"""全真模拟考试 — 严格仿 NCRE-2（支持 Python / C 两种科目）。

通用规则：机考 120 分钟（7200 秒）、满分 100、60 分合格。
每科目题型计划不同（见 EXAM_CONFIGS）：
- python：选择 40 + 操作 60（基本操作 3×5 + 简单应用 2×12.5 + 综合应用 1×20）
- c：选择 40 + 操作 60（程序填空 3×6 + 程序改错 2×9 + 程序设计 1×24）

题目来自项目题库；操作题按关键词/关键思路覆盖率给部分分，近似阅卷的「步骤分」。
"""
import json
import logging
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.quiz import _STOP_CHARS, grade_choice
from app.models import Question, Document, QuizRecord, MockRecord

logger = logging.getLogger("yuanqi.mock")

EXAM_DURATION_SECONDS = 7200   # 120 分钟
PASS_LINE = 60
CHOICE_SCORE = 1.0
ESSAY_PASS_RATIO = 0.6  # 操作题判「对」所需的重合率

# 各科目考试配置：标题 / 题库章节名 / 操作题题型计划（subtype, 题数, 每题满分）
EXAM_CONFIGS: dict[str, dict] = {
    "python": {
        "subject": "python",
        "title": "计算机二级 · Python 语言程序设计 · 全真模拟",
        "choice_doc": "📝 题库 · 选择题（40 分）",
        "essay_doc": "📝 题库 · 操作题（60 分）",
        "essay_plan": [("basic", 3, 5.0), ("applied", 2, 12.5), ("comprehensive", 1, 20.0)],
    },
    "c": {
        "subject": "c",
        "title": "计算机二级 · C 语言程序设计 · 全真模拟",
        "choice_doc": "📝 题库 · C选择题（40 分）",
        "essay_doc": "📝 题库 · C操作题（60 分）",
        "essay_plan": [("fill", 3, 6.0), ("correct", 2, 9.0), ("design", 1, 24.0)],
    },
}


def resolve_config(subject: str | None) -> dict:
    return EXAM_CONFIGS.get(subject or "") or EXAM_CONFIGS["python"]


def _choice_card(q: Question) -> dict:
    try:
        options = json.loads(q.options or "[]")
    except json.JSONDecodeError:
        options = []
    return {"id": q.id, "qtype": q.qtype, "question": q.question, "options": options, "max_score": CHOICE_SCORE}


def _essay_card(q: Question, max_score: float) -> dict:
    return {"id": q.id, "qtype": q.qtype, "question": q.question, "options": [], "max_score": max_score}


async def _find_bank_doc(db: AsyncSession, title: str) -> Document | None:
    return (await db.execute(select(Document).where(Document.title == title))).scalars().first()


async def build_mock_exam(db: AsyncSession, subject: str | None = None) -> dict:
    """组装一份模拟卷：40 道选择题 + 按科目题型计划的操作题。"""
    cfg = resolve_config(subject)
    choice_doc = await _find_bank_doc(db, cfg["choice_doc"])
    essay_doc = await _find_bank_doc(db, cfg["essay_doc"])

    choice_qs: list[dict] = []
    if choice_doc:
        rows = (await db.execute(
            select(Question).where(Question.document_id == choice_doc.id, Question.discarded == False)  # noqa: E712
        )).scalars().all()
        choice_qs = [_choice_card(q) for q in rows[:40]]

    essay_qs: list[dict] = []
    essay_rows: list[Question] = []
    if essay_doc:
        essay_rows = (await db.execute(
            select(Question).where(Question.document_id == essay_doc.id, Question.discarded == False)  # noqa: E712
        )).scalars().all()

    # 按题型分配操作题：每种题型取计划题数，不足则用其余操作题补齐
    pools: dict[str, list[Question]] = {}
    for q in essay_rows:
        pools.setdefault(q.subtype or "applied", []).append(q)
    remaining: list[Question] = []
    assigned: list[tuple[Question, float]] = []
    for sub, count, score in cfg["essay_plan"]:
        pool = pools.get(sub, [])
        take = pool[:count]
        assigned.extend((q, score) for q in take)
        remaining.extend(pool[count:])
    need = sum(c for _, c, _ in cfg["essay_plan"]) - len(assigned)
    if need > 0:
        for q in remaining[:need]:
            assigned.append((q, 12.5))  # 补齐的按默认 12.5 分算
    essay_qs = [_essay_card(q, score) for q, score in assigned]

    return {
        "title": cfg["title"],
        "subject": cfg["subject"],
        "duration_seconds": EXAM_DURATION_SECONDS,
        "pass_line": PASS_LINE,
        "sections": [
            {"id": "choice", "name": "第一部分 · 单项选择题（40 分）", "max_score": 40.0, "questions": choice_qs},
            {"id": "essay", "name": "第二部分 · 操作题（60 分）", "max_score": 60.0, "questions": essay_qs},
        ],
    }


_CJK_RE = re.compile(r"[一-鿿]")


def _cjk_chars(text: str) -> set[str]:
    """中文按单字取（去掉停用字），代码/英文整词仍按词算。"""
    chars = {ch for ch in _CJK_RE.findall(text) if ch not in _STOP_CHARS}
    words = {w for w in re.findall(r"[A-Za-z_]\w*", text) if len(w) > 1}
    return chars | words


def _essay_ratio(correct_answer: str, user_answer: str) -> float:
    """参考答案与用户作答的重合率（部分分依据，0~1）。"""
    ans = _cjk_chars(correct_answer)
    if not ans or len(user_answer) < 4:
        return 0.0
    usr = _cjk_chars(user_answer)
    if not usr:
        return 0.0
    return len(ans & usr) / len(ans)


async def grade_mock_exam(db: AsyncSession, answers: dict[str, str], subject: str | None = None) -> dict:
    """交卷判分：选择题精确匹配，操作题按重合率给部分分。每题写 QuizRecord。"""
    exam = await build_mock_exam(db, subject)

    result_sections: list[dict] = []
    total = 0.0
    for sec in exam["sections"]:
        sec_score = 0.0
        items: list[dict] = []
        for q in sec["questions"]:
            qid = q["id"]
            user_answer = (answers.get(qid) or "").strip()
            max_score = q["max_score"]
            row = await db.get(Question, qid)
            if row is None:
                continue
            if q["qtype"] == "choice":
                try:
                    options = json.loads(row.options or "[]")
                except json.JSONDecodeError:
                    options = []
                correct = grade_choice(options, row.answer, user_answer)
                score = max_score if correct else 0.0
                sec_score += score
                total += score
                db.add(QuizRecord(question_id=qid, user_answer=user_answer, correct=correct))
                items.append({
                    "id": qid, "qtype": "choice", "question": q["question"], "options": options,
                    "user_answer": user_answer, "correct": correct, "score": score, "max_score": max_score,
                    "answer": row.answer, "explanation": row.explanation,
                })
            else:
                ratio = _essay_ratio(row.answer, user_answer)
                score = round(max_score * ratio, 1)
                correct = ratio >= ESSAY_PASS_RATIO
                sec_score += score
                total += score
                db.add(QuizRecord(question_id=qid, user_answer=user_answer, correct=correct))
                items.append({
                    "id": qid, "qtype": "essay", "question": q["question"], "options": [],
                    "user_answer": user_answer, "correct": correct, "score": score, "max_score": max_score,
                    "answer": row.answer, "explanation": row.explanation,
                })
        result_sections.append({
            "id": sec["id"], "name": sec["name"],
            "score": round(sec_score, 1), "max_score": sec["max_score"], "questions": items,
        })

    await db.commit()
    total = round(total, 1)
    return {
        "title": exam["title"],
        "total": total,
        "max_score": 100.0,
        "pass_line": PASS_LINE,
        "passed": total >= PASS_LINE,
        "sections": result_sections,
    }
