"""老教授课堂 — 一对一手把手交互式授课（像看视频课，但可对话）。

每节格式：一小节知识点 → 真题示例 → 课堂练习 → 检验提问。
人设：12 年 NCRE 阅卷经验的高校教授；答错先给分步提示，不直接甩答案。
内容由 LLM 按课程卡 schema 生成，课程卡（含参考答案）存进 Lesson 记录。
"""
import json
import logging
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.lesson import CURRICULUM, _chat
from app.models import Lesson, TopicProgress, StudyLog, User

logger = logging.getLogger("yuanqi.course")


def _extract_json_robust(text: str) -> dict:
    """从 LLM 输出里提取 JSON 对象：先试整体解析，失败则按花括号配平扫描最外层。"""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        pass
    start = None
    depth = 0
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    data = json.loads(text[start:i + 1])
                    return data if isinstance(data, dict) else {}
                except Exception:
                    start = None
    return {}

# 答错超过该次数后，才允许给参考答案
MAX_ATTEMPTS = 3

PROFESSOR_PERSONA = """你是「老教授」——一位有 12 年全国计算机等级考试（NCRE）二级 Python 阅卷经验的高校计算机专业教授，专职带零基础学员稳定通过考试。
你的授课原则：
1. 严格贴合官方大纲，只讲考场会考的内容，剔除无关高深知识
2. 一次只讲一小节知识点，绝不一口气倒一大堆
3. 讲解通俗、生活化比喻，面向零基础，不堆术语
4. 讲解和点评要标注【扣分陷阱】和【阅卷得分要点】：什么写法拿满分、什么写法直接丢分
5. 学生答错时：绝不一上来甩标准答案，先给分步提示引导，让他自己走到答案
6. 说话像一位耐心又严格的教授，专业、亲切、接地气，多用「咱们」「这个点考试一定会考」"""

_LESSON_SCHEMA = """请只输出一个 JSON 对象（不要任何多余文字，不要使用 ``` 代码围栏）：
{
  "topic": "本节知识点名称",
  "lecture": "一小节通俗讲解（300字内，含一个生活化比喻）+ 一个考场真题示例和可直接运行的代码（代码用缩进表示）",
  "traps": "本节扣分陷阱 / 阅卷得分要点 / 高频易错坑，2-4 条（每条约20字）",
  "practice": "一道课堂练习题（让学生动手写，贴合真题题型，给出示例输入/输出）",
  "practice_answer": "练习题的参考答案（完整可运行代码，仅用于教师核对，不展示给学生）",
  "check": "一道检验提问（考本节核心考点，简短，能检验是否真懂）",
  "check_answer": "检验提问的参考答案要点"
}
硬性要求：
- 必须是**合法 JSON**：字符串值内的换行一律用 \\n 转义，不要输出真实的回车；不要用 ``` 围栏
- 代码里若有大括号 { }，作为普通字符写进字符串即可"""


# ---------------------------------------------------------------- 大纲

def get_course(subject: str) -> list[dict]:
    """课程大纲：该学科 CURRICULUM 的有序考点序列。"""
    return [{"topic": it["topic"], "desc": it["desc"]} for it in CURRICULUM.get(subject, [])]


async def _progress_rows(db: AsyncSession, user_id: str, subject: str) -> dict[str, TopicProgress]:
    rows = (await db.execute(
        select(TopicProgress).where(TopicProgress.user_id == user_id, TopicProgress.subject == subject)
    )).scalars().all()
    return {r.topic: r for r in rows}


async def get_outline(db: AsyncSession, user: User, subject: str) -> dict:
    """大纲 + 已掌握标记 + 当前应学第几节。"""
    items = get_course(subject)
    progs = await _progress_rows(db, user.id, subject)
    topics = [{"topic": it["topic"], "desc": it["desc"],
               "done": progs.get(it["topic"], None) and progs[it["topic"]].status == "mastered"}
              for it in items]
    current = next((i for i, t in enumerate(topics) if not t["done"]), len(topics))
    return {"subject": subject, "topics": topics, "current_index": current, "total": len(topics)}


# ---------------------------------------------------------------- 开课

async def _find_lesson(db: AsyncSession, user_id: str, subject: str, topic: str) -> Lesson | None:
    return (await db.execute(
        select(Lesson).where(Lesson.user_id == user_id, Lesson.subject == subject,
                             Lesson.topic == topic, Lesson.step == "course")
        .order_by(Lesson.updated_at.desc())
    )).scalars().first()


async def start_lesson(db: AsyncSession, user: User, subject: str, topic: str) -> dict:
    """生成（或复用）一节老教授课程卡，返回公开部分（不含参考答案）。"""
    lesson = await _find_lesson(db, user.id, subject, topic)
    if lesson is None:
        prompt = f"""请为这节课生成课程卡。学科：{subject}，本节知识点：{topic}。
- lecture 必须严格围绕「{topic}」本身，绝不跑题；宁可讲浅，不要扯到别的知识点
- 真题示例要是真实考场会出的题型（选择题示例或填空/操作题示例皆可）
{_LESSON_SCHEMA}"""
        card = {}
        try:
            raw = await _chat([{"role": "system", "content": PROFESSOR_PERSONA},
                               {"role": "user", "content": prompt}], temperature=0.7, max_tokens=2000)
            card = _extract_json_robust(raw)
            if not card:
                raise ValueError("课程卡 JSON 为空")
        except Exception as e:
            logger.warning("课程卡生成失败，用模板兜底: %s", e)
        card.setdefault("topic", topic)
        card.setdefault("lecture", f"「{topic}」这一节，我们先记住最核心的一点，再展开。")
        card.setdefault("traps", ["这个点考试一定会考，注意基础写法"])
        card.setdefault("practice", f"用你自己的话写一个关于「{topic}」的小练习。")
        card.setdefault("practice_answer", "")
        card.setdefault("check", f"一句话说说：「{topic}」最关键的一点是什么？")
        card.setdefault("check_answer", "能用自己的大白话讲清核心即可。")

        lesson = Lesson(user_id=user.id, subject=subject, topic=topic, step="course", status="active")
        lesson.set_card(card)
        db.add(lesson)

    # 记录学习进度：次数 +1、状态学习中
    prog = (await _progress_rows(db, user.id, subject)).get(topic)
    if prog:
        prog.times += 1
    else:
        db.add(TopicProgress(user_id=user.id, subject=subject, topic=topic, status="learning", times=1))
    db.add(StudyLog(user_id=user.id, kind="lesson", detail=f"老教授课堂：开始「{subject}·{topic}」", points=3))
    await db.commit()

    card = lesson.get_card()
    traps = card.get("traps") or []
    if isinstance(traps, str):      # 模型偶尔把列表写成了字符串
        traps = [traps]
    return {
        "subject": subject,
        "topic": topic,
        "lesson_id": lesson.id,
        "lecture": card.get("lecture", ""),
        "traps": traps[:4],          # 只展示最关键的几条陷阱
        "practice": card.get("practice", ""),
        "check": card.get("check", ""),
    }


# ---------------------------------------------------------------- 作答

async def answer(db: AsyncSession, user: User, subject: str, topic: str,
                 kind: str, answer_text: str, attempt: int = 1) -> dict:
    """老教授批改课堂练习（practice）或检验提问（check）。

    答对 → 肯定 + 拿满分要点；答错 → 只给分步提示（不直接给答案）；
    答错达 MAX_ATTEMPTS 次 → 拆解参考答案。
    """
    lesson = await _find_lesson(db, user.id, subject, topic)
    if lesson is None:
        return {"correct": False, "feedback": "还没开这节课，请先让老教授讲课。", "reveal": False, "reference": ""}
    card = lesson.get_card()
    question = card.get(kind, "")
    reference = card.get(kind + "_answer", "")

    prompt = f"""你是阅卷老师，判断学生的答案是否正确。
【题目】{question}
【参考答案】{reference}
【学生的回答】{answer_text}

只输出一个 JSON 对象（不要任何多余文字）：
{{"correct": true 或 false, "feedback": "点评（答对：具体肯定 + 指出拿满分要点；答错：给一个分步提示引导，绝不给出完整答案，60字内）"}}"""
    verdict = {"correct": bool(answer_text.strip()), "feedback": "收到，先自己再想想关键点～"}
    try:
        raw = await _chat([{"role": "system", "content": PROFESSOR_PERSONA},
                           {"role": "user", "content": prompt}], temperature=0.3, max_tokens=400)
        data = _extract_json_robust(raw)
        if data.get("correct") is not None:
            verdict = {"correct": bool(data["correct"]), "feedback": str(data.get("feedback", ""))}
    except Exception as e:
        logger.warning("老教授批改失败，宽松判分: %s", e)

    # 答错且达到次数上限 → 给参考答案拆解
    reveal = (not verdict["correct"]) and attempt >= MAX_ATTEMPTS
    # 答对 → 攒元气
    if verdict["correct"]:
        db.add(StudyLog(user_id=user.id, kind="lesson",
                        detail=f"老教授课堂「{topic}」{('练习' if kind == 'practice' else '检验')}答对", points=3))
        await db.commit()

    return {"correct": verdict["correct"], "feedback": verdict["feedback"],
            "reveal": reveal, "reference": reference if reveal else ""}


# ---------------------------------------------------------------- 完成

async def complete_lesson(db: AsyncSession, user: User, subject: str, topic: str) -> dict:
    """标记本节已掌握，推进课程。"""
    prog = (await _progress_rows(db, user.id, subject)).get(topic)
    if prog:
        prog.status = "mastered"
    else:
        db.add(TopicProgress(user_id=user.id, subject=subject, topic=topic, status="mastered", times=1))
    await db.commit()
    outline = await get_outline(db, user, subject)
    return {"topic": topic, "done": True, "current_index": outline["current_index"],
            "next_topic": outline["topics"][outline["current_index"]]["topic"] if outline["current_index"] < outline["total"] else None}
