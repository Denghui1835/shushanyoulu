"""深度教学模式 — 苏格拉底式一对一教学（讲→考→判→评）

这是元气搭子的「教师模式」：不满足于陪聊，而是像私教一样
  1. 讲：用大白话 + 比喻讲一个知识点（teach）
  2. 考：出一道思考题考学习者（question）
  3. 判：学习者作答后，判断对错（evaluate）
  4. 评：点评纠正，然后进入下一个知识点，循环往复

内容来源：
  - 优先用「课程卡内容库」（学习平台/内容库/{subject}/*.json，每文件一张卡）
  - 没有卡时，由 LLM 结合学习者资料实时生成教学卡
"""
import json
import logging
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.api_scheduler import api_client
from app.core.api_scheduler.adapters.base import AdapterConfig
from app.core.retrieval import retrieve
from app.models import Lesson, StudyLog, TopicProgress, User

logger = logging.getLogger("yuanqi.lesson")

# 课程卡内容库根目录（学习平台攒的卡）
CONTENT_DIR = Path("D:/南农模型/学习平台/内容库")

# 默认最多教几轮（可中途由学习者结束）
DEFAULT_MAX_ROUNDS = 6

# 内置课程目录：零基础学习者「点菜式」选择想学的知识点（按入门顺序排列）。
# 这是内容层的起步——以后每门课有了课程卡，再逐步替换/扩充这里的条目。
CURRICULUM: dict[str, list[dict]] = {
    "3DGS": [
        {"topic": "高斯泼溅是什么", "desc": "一分钟搞懂 3D 高斯泼溅"},
        {"topic": "从照片到模型的三步", "desc": "算位置 → 铺气泡 → 调气泡"},
        {"topic": "高斯点（彩色小气泡）", "desc": "3D 模型的基本单元"},
        {"topic": "相机位姿是什么", "desc": "每张照片站在哪拍的"},
        {"topic": "一次迭代在干嘛", "desc": "渲染 → 算损失 → 反传更新"},
        {"topic": "COLMAP 在做什么", "desc": "照片对齐，算出拍摄位置"},
        {"topic": "怎么查看自己的模型", "desc": "ply / splat 文件怎么用"},
    ],
    # 数学建模：零基础从零教起的完整路径（先入门→再模型→后比赛，内容库 内容库/数学建模/*.json 有对应卡）
    "数学建模": [
        # ── 〇 从零开始：数学建模到底是什么（零基础友好，一个术语都不丢）──
        {"topic": "数学建模是什么", "desc": "把问题翻译成数学、算完再翻译回来（开奶茶店定价例）"},
        {"topic": "生活中的数学建模", "desc": "外卖路线/天气预报/游戏平衡——你天天都在用"},
        {"topic": "数学建模和数学课的区别", "desc": "不是做题，是解决现实问题，没有唯一答案"},
        {"topic": "建模的三个动作", "desc": "翻译→简化→算，记住这三步就够了"},
        {"topic": "零基础不用怕", "desc": "数学够用的就几样，编程会改数字就行"},
        # ── 一 第一支模型：6步手把手走一遍 ──
        {"topic": "完整流程6步骨架", "desc": "审题→假设→建模→求解→检验→论文（做菜比喻）"},
        {"topic": "怎么审题", "desc": "圈名词：分清已知/要求，把题目读成『要算什么』"},
        {"topic": "怎么提假设", "desc": "合理简化+写清楚+诚实，假设定模型边界"},
        {"topic": "第一次建模：从问题到答案", "desc": "食堂一天要做多少饭？手把手带你算一遍"},
        {"topic": "怎么检查结果对不对", "desc": "对账法：和已知的对一对，或换种方法算一遍"},
        # ── 二 模型工具箱（零基础版，先会用再深究）──
        {"topic": "优化模型入门", "desc": "怎么算最划算：目标+变量+约束"},
        {"topic": "预测模型入门", "desc": "怎么猜未来：先看图，再选方法"},
        {"topic": "评价模型：AHP层次分析法", "desc": "一堆方案选哪个：打分+权重+排序"},
        {"topic": "用 Python 算第一个模型", "desc": "复制就能跑，改数字就出结果"},
        {"topic": "结果可视化规范", "desc": "画图讲结论：一图一结论"},
        # ── 三 把模型做扎实（进阶，有基础后再学）──
        {"topic": "模型检验与误差分析", "desc": "结果凭什么可信：误差/对照/外部参照"},
        {"topic": "灵敏度与稳定性分析", "desc": "参数猜错结论变不变——进阶必会"},
        {"topic": "不确定性：贝叶斯方法", "desc": "参数是估的怎么办：把不确定算进去"},
        {"topic": "多目标优化怎么处理", "desc": "鱼和熊掌：加权/约束法/帕累托"},
        {"topic": "模拟退火与启发式算法", "desc": "解太多算不动：启发式搜索"},
        {"topic": "微分方程与动态模型", "desc": "变化率建模：生态/人口/传染病"},
        {"topic": "图论与网络分析", "desc": "关系建模：最短路/中心性/网络"},
        {"topic": "聚类分析", "desc": "把东西自动分组：K-means"},
        {"topic": "回归与机器学习", "desc": "找变量关系：回归/Logistic"},
        {"topic": "蒙特卡洛模拟", "desc": "随机模拟算复杂概率"},
        {"topic": "模型建立的基本套路", "desc": "目标→变量→关系→式子，通用骨架"},
        # ── 四 去比赛（备赛，零基础学完前面也能上）──
        {"topic": "美赛vs国赛：赛制对比", "desc": "比赛有哪些：72h国赛/96h美赛"},
        {"topic": "美赛六题怎么选", "desc": "A/B/C/D/E/F 选哪个，扬长避短"},
        {"topic": "奖项等级与O奖标准", "desc": "奖项金字塔：O奖是『范例』不是『全对』"},
        {"topic": "队伍分工", "desc": "建模/编程/写作三摊，写作占分最重"},
        {"topic": "赛程时间分配", "desc": "前松后紧是大忌，最后6小时只写论文"},
        {"topic": "赛前准备清单", "desc": "工具链/资料库/论文模板/模拟比赛"},
        {"topic": "论文格式规范（硬性要求）", "desc": "格式红线：承诺书/摘要1页/附录代码"},
        {"topic": "怎么写摘要", "desc": "摘要=命根子：每问一段 方法+数字"},
        {"topic": "怎么写建模论文", "desc": "论文骨架：先说结论再讲过程"},
        {"topic": "问题重述与问题分析写法", "desc": "证明你读懂了题：提炼不抄题"},
        {"topic": "正文结构与模型建立章节", "desc": "黄金骨架+给模型起体系化名字"},
        {"topic": "图表规范", "desc": "图表是证据：矢量图/三线表"},
        {"topic": "附录与支撑材料", "desc": "代码可运行是硬要求，证据链"},
        {"topic": "参考文献与引用", "desc": "数据/方法要有出处，按规范标注"},
        {"topic": "O奖论文的共同特征", "desc": "9篇O奖炼出的『得奖基因』"},
        {"topic": "从O奖论文学什么", "desc": "学套路不抄答案"},
        {"topic": "模拟比赛与复盘", "desc": "完整彩排一遍，问题转成改法"},
    ],
    "数学分析": [
        {"topic": "极限是什么", "desc": "逼近但不等于"},
        {"topic": "导数与微分", "desc": "变化的快慢"},
        {"topic": "定积分入门", "desc": "累加出面积"},
        {"topic": "中值定理", "desc": "罗尔、拉格朗日"},
    ],
    "高等代数": [
        {"topic": "什么是向量", "desc": "有方向有大小"},
        {"topic": "矩阵是什么", "desc": "向量的变换"},
        {"topic": "行列式入门", "desc": "矩阵的缩放因子"},
        {"topic": "特征值与特征向量", "desc": "变换中不变的方向"},
    ],
    "数理统计": [
        {"topic": "什么是统计推断", "desc": "用样本猜总体"},
        {"topic": "随机变量与分布", "desc": "描述不确定性"},
        {"topic": "假设检验入门", "desc": "先怀疑再验证"},
        {"topic": "回归分析入门", "desc": "找变量之间的关系"},
    ],
    "Python程序设计": [
        {"topic": "程序格式与缩进", "desc": "注释、命名规则、保留字、缩进"},
        {"topic": "变量与基本数据类型", "desc": "数字类型、字符串、类型转换"},
        {"topic": "输入输出与格式化", "desc": "input / print / f-string"},
        {"topic": "分支结构", "desc": "if / elif / else、逻辑运算"},
        {"topic": "循环结构", "desc": "for / while / range / break / continue"},
        {"topic": "列表", "desc": "增删改查、切片、列表推导式"},
        {"topic": "字符串进阶", "desc": "切片、常用方法、查找替换"},
        {"topic": "元组与集合", "desc": "不可变元组、集合去重"},
        {"topic": "字典", "desc": "键值对、遍历、常用方法"},
        {"topic": "函数与参数", "desc": "定义、参数、默认值、lambda、递归"},
        {"topic": "文件读写与数据格式化", "desc": "open / with / CSV / JSON"},
        {"topic": "异常处理", "desc": "try / except / else / finally"},
        {"topic": "标准库与第三方库", "desc": "random / time / jieba / wordcloud / PyInstaller"},
        {"topic": "综合应用题实战", "desc": "真题三大题型与解题套路"},
    ],
    "C语言程序设计": [
        {"topic": "C 程序结构与编译运行", "desc": "预处理、main 主函数、编译链接"},
        {"topic": "数据类型与常量变量", "desc": "int / float / char、常量、变量定义"},
        {"topic": "运算符与表达式", "desc": "算术/关系/逻辑/赋值/位、优先级"},
        {"topic": "输入输出函数", "desc": "printf / scanf、格式控制符"},
        {"topic": "选择结构", "desc": "if / else / switch"},
        {"topic": "循环结构", "desc": "for / while / do-while / break / continue"},
        {"topic": "数组", "desc": "一维/二维数组、字符数组与字符串"},
        {"topic": "函数与作用域", "desc": "定义、调用、参数传递、返回值"},
        {"topic": "指针", "desc": "指针变量、指针与数组、指针与函数"},
        {"topic": "结构体与共用体", "desc": "struct / union / typedef"},
        {"topic": "文件操作", "desc": "fopen / fprintf / fscanf / fread"},
        {"topic": "预处理与动态内存", "desc": "#define / malloc / free"},
        {"topic": "字符串库函数", "desc": "strlen / strcpy / strcmp / strcat"},
        {"topic": "综合题实战", "desc": "程序填空/改错/设计题的套路"},
    ],
}


def get_curriculum() -> dict[str, dict[str, list[dict]]]:
    """课程目录按学科门类组织：门类 → 一级学科 → 知识点列表。

    兼容前端从"3DGS/数学建模"旧学科选择，自动归位到三级分类
    （如 3DGS → 工学/人工智能）。返回结构：
    {"工学": {"人工智能": [{"topic":..., "desc":...}, ...], ...}, ...}
    """
    from app.core.categories import legacy_mapping

    result: dict[str, dict[str, list[dict]]] = {}
    for subject, items in CURRICULUM.items():
        mapped = legacy_mapping(subject)
        if not mapped:
            continue
        cat, sub = mapped
        bucket = result.setdefault(cat, {}).setdefault(sub, [])
        for it in items:
            # subject=子学科名（教学上下文）；subject_key=真实学科键（前端开课用它，
            # 才能命中 内容库/{真实学科}/*.json 里的精选卡，而不是每次让 LLM 现生成）
            bucket.append({**it, "subject": sub, "subject_key": subject})
    return result

TEACHER_PERSONA = """你是「小书虫」的教师模式——一位认真负责的私教，同时还是学习者最亲的朋友。
你信奉「真正学会 = 能讲给别人听」。所以你的教法不是灌答案，而是：
1. 讲解必须大白话 + 生活化比喻，让学习者一听就懂，绝不堆术语
2. 讲完立刻出一道**选择题**（4 个选项，含一个最容易选错的干扰项），让学习者点选，一次只考一个点
3. 学习者答错时不批评，先肯定 TA 思考的部分，再指出错在哪、怎么纠
4. 答对时不敷衍，追问一句让 TA 再深想一层，巩固理解
你说话元气满满、口语化、多用呀呢啦，但教学本身要严谨。"""

# 课程卡 JSON 字段约束（选择题模式：固定答案，判分不烧 token）
_CARD_SCHEMA = """请只输出一个 JSON 对象（不要任何多余文字）：
{
  "topic": "本卡知识点名称（简短）",
  "teach": "大白话讲解，含一个生活化比喻，150字以内（一次只讲一小点）",
  "question": "一道选择题的题干（只考刚才讲的那一点）",
  "options": ["选项A", "选项B", "选项C", "选项D"],
  "answer_index": 0,
  "explanation": "为什么选这个选项（简洁，一两句）",
  "common_error": "最容易选错的一个选项及原因",
  "comment": "点评：答对怎么肯定+追问；答错怎么纠正+引导（30字内）"
}
注意：answer_index 必须是整数（0~3），options 必须恰好 4 个字符串。"""


# ---------------------------------------------------------------- helpers

def _extract_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"无法解析 JSON: {text[:200]}")
    return json.loads(text[start:end + 1])


async def _chat(messages: list[dict], temperature: float = 0.7, max_tokens: int = 1200) -> str:
    adapter = api_client.get_adapter(settings.default_model)
    resp = await adapter.chat_completion(messages, AdapterConfig(temperature=temperature, max_tokens=max_tokens))
    return resp.content


# ---------------------------------------------------------------- cards

def list_card_files(subject: str) -> list[Path]:
    """列出某学科内容库里的课程卡文件（.json，每文件一张卡）。"""
    subj_dir = CONTENT_DIR / subject
    if not subj_dir.is_dir():
        return []
    return sorted(subj_dir.glob("*.json"))


def load_cards(subject: str) -> list[dict]:
    """读取某学科内容库的全部课程卡。"""
    cards: list[dict] = []
    for f in list_card_files(subject):
        try:
            cards.append(json.loads(f.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("课程卡解析失败 %s: %s", f.name, e)
    return cards


def pick_card(cards: list[dict], topic: str) -> dict | None:
    """在课程卡库里挑一张和 topic 最相关的卡（模糊包含匹配）。"""
    if not topic:
        return cards[0] if cards else None
    for c in cards:
        if topic in (c.get("topic") or "") or (c.get("topic") or "") in topic:
            return c
    return cards[0] if cards else None


# ---------------------------------------------------------------- lesson core

def _normalize_card(card: dict) -> dict:
    """规整选择题字段：options 必须是字符串列表、answer_index 必须是合法下标。

    兼容旧卡（无 options）与 LLM 输出（下标可能是字符串）。
    """
    opts = card.get("options")
    if not isinstance(opts, list) or not opts:
        card["options"] = []
        card["answer_index"] = -1
        return card
    card["options"] = [str(o).strip() for o in opts if str(o).strip()][:4]
    while len(card["options"]) < 4:
        card["options"].append("（选项缺失）")
    ai = card.get("answer_index")
    try:
        ai = int(ai)
    except (TypeError, ValueError):
        ai = -1
    if ai < 0 or ai >= len(card["options"]):
        ai = 0
    card["answer_index"] = ai
    return card


async def _rerank_chunks(db: AsyncSession, query: str, chunks: list[dict], top_k: int = 2) -> list[dict]:
    """语义重排：用 LLM 从召回片段里选出和主题最相关的 top_k。

    这是「词法检索 → 语义检索」的轻量升级：不引入向量库，
    让 LLM 理解语义后筛选，显著提升教学引用的相关性。
    """
    if not chunks or len(chunks) <= top_k:
        return chunks
    items = "\n".join(f"[{i}] {c['content'][:200]}" for i, c in enumerate(chunks))
    prompt = f"""主题：{query}
以下是从学习者资料中召回的片段，请选出和主题最相关的 {top_k} 个，按相关性从高到低排列：
{items}
只输出 JSON：{{"indices": [序号列表]}}"""
    messages = [{"role": "system", "content": "你是一个精准的资料筛选器。"}, {"role": "user", "content": prompt}]
    try:
        raw = await _chat(messages, temperature=0.0, max_tokens=200)
        data = _extract_json(raw)
        idxs = [int(i) for i in data.get("indices", []) if str(i).lstrip("-").isdigit() and 0 <= int(i) < len(chunks)]
        idxs = idxs[:top_k]
    except Exception as e:
        logger.warning("rerank failed, fallback to first %d: %s", top_k, e)
        idxs = list(range(min(top_k, len(chunks))))
    return [chunks[i] for i in idxs]


async def _generate_card(db: AsyncSession, user: User, subject: str, topic: str) -> dict:
    """由 LLM 生成一张教学卡，结合学习者资料做 grounding。"""
    # 检索相关资料节选，让讲解落地到学习者自己的资料上（词法召回 + LLM 语义重排）
    chunks = []
    try:
        cands = await retrieve(db, topic, top_k=6, min_score=0.05)
        chunks = await _rerank_chunks(db, topic, cands, top_k=2)
    except Exception as e:
        logger.warning("lesson retrieval failed: %s", e)

    grounding = ""
    if chunks:
        grounding = "【学习者资料节选（讲课时优先引用）】\n" + "\n".join(
            f"- 《{c.get('title', '')}》{c['content'][:300]}" for c in chunks
        )

    prompt = f"""请为学习者生成一张教学卡，主题必须**严格围绕**「{topic}」（学科：{subject}）。
硬性要求：
- 内容绝不跑题，就讲「{topic}」本身；宁可讲得浅，也不要扯到别的主题
- 如果下面提供的资料节选和「{topic}」无关，请完全忽略它（资料只是辅助参考）
- question 必须直接考察「{topic}」刚才讲的内容
{grounding}
{_CARD_SCHEMA}"""

    messages = [{"role": "system", "content": TEACHER_PERSONA}, {"role": "user", "content": prompt}]
    try:
        raw = await _chat(messages, temperature=0.7, max_tokens=1500)
        card = _extract_json(raw)
    except Exception as e:
        logger.warning("教学卡生成失败，回退到模板卡: %s", e)
        card = {
            "topic": topic or subject,
            "teach": f"（AI 生成失败，先用一段话兜底）关于「{topic or subject}」，先记住最核心的一点。",
            "question": f"关于「{topic or subject}」，下列说法正确的是？",
            "options": ["它和普通数学题没有区别", "它是把现实问题翻译成数学并求解", "它只能靠死记硬背", "它不需要任何数学"],
            "answer_index": 1,
            "explanation": "数学建模＝把现实问题翻译成数学，算完再翻译回现实。",
            "common_error": "误以为它只是更难的应用题",
            "comment": "答对：很好！答错：记住『翻译→算→翻译回现实』三步。",
        }
    return _normalize_card(card)


async def _judge_answer(db: AsyncSession, card: dict, answer: str) -> dict:
    """判断答案对错并点评。

    选择题：固定答案直接比对下标，不调用 LLM（省 token 的关键）。
    开放式问答（旧卡兜底）：才由 LLM 判断。
    """
    options = card.get("options")
    if options:
        try:
            idx = int(str(answer).strip())
        except (TypeError, ValueError):
            idx = -1
        correct = idx == card.get("answer_index")
        explanation = card.get("explanation", "") or ""
        comment = card.get("comment", "") or ""
        if correct:
            return {"correct": True, "comment": comment or (explanation or "答对啦！")}
        right_text = ""
        ai = card.get("answer_index")
        if isinstance(ai, int) and 0 <= ai < len(options):
            right_text = options[ai]
        hint = f"正确答案是「{right_text}」。" if right_text else ""
        hint += explanation
        full = (hint + (f"\n{comment}" if comment else "")).strip()
        return {"correct": False, "comment": full or "再想想，换个选项？"}

    # 开放式问答：LLM 判断（兜底，仅兼容旧卡）
    prompt = f"""判断学生的学习回答，并给出点评。
【题目】{card.get('question', '')}
【参考答案】{card.get('answer', '')}
【常见错误】{card.get('common_error', '')}
【学生的回答】{answer}

只输出 JSON：{{"correct": true 或 false, "comment": "对学生的点评（答对：具体肯定+追问一层；答错：先共情再指出错哪、怎么改，50字内）"}}"""

    messages = [{"role": "system", "content": TEACHER_PERSONA}, {"role": "user", "content": prompt}]
    try:
        raw = await _chat(messages, temperature=0.3, max_tokens=600)
        return _extract_json(raw)
    except Exception as e:
        logger.warning("判断失败，回退到宽松判断: %s", e)
        return {
            "correct": bool(answer.strip()),
            "comment": "收到你的回答啦！对照参考答案再看看有没有遗漏的点。",
        }


# ---------------------------------------------------------------- public API

async def start_lesson(db: AsyncSession, user: User, subject: str, topic: str) -> dict:
    """开启一次深度教学：创建教学会话，返回第一张卡（讲+题）。"""
    cards = load_cards(subject)
    card = pick_card(cards, topic)
    if card is None:
        card = await _generate_card(db, user, subject, topic)
    card = _normalize_card(card or {})

    lesson = Lesson(
        user_id=user.id,
        subject=subject,
        topic=topic,
        step="question",   # 卡已就绪，等学习者作答
        status="active",
    )
    lesson.set_card(card)
    db.add(lesson)

    # 记录考点学习进度：学习次数 +1
    prog = (await db.execute(
        select(TopicProgress).where(
            TopicProgress.user_id == user.id,
            TopicProgress.subject == subject,
            TopicProgress.topic == topic,
        )
    )).scalars().first()
    if prog:
        prog.times += 1
    else:
        db.add(TopicProgress(user_id=user.id, subject=subject, topic=topic, status="learning", times=1))

    await db.commit()
    await db.refresh(lesson)

    db.add(StudyLog(user_id=user.id, kind="lesson", detail=f"开始了「{subject}·{topic}」的深度教学", points=3))
    await db.commit()

    return {
        "lesson_id": lesson.id,
        "subject": subject,
        "topic": topic,
        "step": "question",
        "teach": card.get("teach", ""),
        "question": card.get("question", ""),
        "options": card.get("options", []),   # 选择题选项（空=开放式旧卡，前端回退文本框）
        "round": 1,
        "max_rounds": DEFAULT_MAX_ROUNDS,
    }


async def answer_lesson(db: AsyncSession, user: User, lesson_id: str, answer: str) -> dict:
    """学习者作答后：判断对错 → 点评 → 生成下一张卡（或结束）。"""
    lesson = await db.get(Lesson, lesson_id)
    if lesson is None or lesson.user_id != user.id:
        raise ValueError("教学会话不存在")

    card = lesson.get_card()

    # 1) 判断对错
    verdict = await _judge_answer(db, card, answer)

    # 2) 记录问答历史
    lesson.append_history({
        "question": card.get("question", ""),
        "answer": answer,
        "correct": verdict.get("correct", False),
        "comment": verdict.get("comment", ""),
    })
    lesson.rounds += 1

    # 3) 记 StudyLog（答对有元气值）
    db.add(StudyLog(
        user_id=user.id, kind="lesson",
        detail=f"「{lesson.topic}」作答：{'✅' if verdict.get('correct') else '❌'} {answer[:40]}",
        points=5 if verdict.get("correct") else 1,
    ))

    # 4) 是否结束（达到轮次上限）
    if lesson.rounds >= DEFAULT_MAX_ROUNDS:
        lesson.step = "done"
        lesson.status = "done"
        await db.commit()
        return {
            "lesson_id": lesson.id,
            "step": "done",
            "correct": verdict.get("correct", False),
            "comment": verdict.get("comment", ""),
            "rounds": lesson.rounds,
            "message": f"这一课一共过了 {lesson.rounds} 轮，休息一下，回头别忘了复习！",
        }

    # 5) 否则生成下一张卡（新知识点），继续教学
    next_topic = f"{lesson.topic}（进阶）"  # 同一主题深入
    next_card = _normalize_card(await _generate_card(db, user, lesson.subject, next_topic))
    lesson.set_card(next_card)
    lesson.step = "question"
    await db.commit()

    return {
        "lesson_id": lesson.id,
        "step": "question",
        "correct": verdict.get("correct", False),
        "comment": verdict.get("comment", ""),
        "teach": next_card.get("teach", ""),
        "question": next_card.get("question", ""),
        "options": next_card.get("options", []),
        "round": lesson.rounds + 1,
        "max_rounds": DEFAULT_MAX_ROUNDS,
    }


async def end_lesson(db: AsyncSession, user: User, lesson_id: str) -> dict:
    """提前结束教学（写统计，标记 done）。"""
    lesson = await db.get(Lesson, lesson_id)
    if lesson is None or lesson.user_id != user.id:
        raise ValueError("教学会话不存在")
    lesson.step = "done"
    lesson.status = "done"
    await db.commit()
    return {"lesson_id": lesson.id, "step": "done", "rounds": lesson.rounds}
