"""题目生成与评分."""
import json
import logging
import re

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.api_scheduler import api_client
from app.core.api_scheduler.adapters.base import AdapterConfig
from app.core.parsing import estimate_tokens
from app.models import Document, Chunk, Question, QuizRecord

logger = logging.getLogger("yuanqi.quiz")

_MAX_CHARS_PER_BATCH = 10000


async def generate_questions(db: AsyncSession, document_id: str, count: int = 8) -> list[Question]:
    """Generate questions for a document (LLM, batched by char budget)."""
    doc = await db.get(Document, document_id)
    if not doc:
        raise ValueError("文档不存在")

    chunks = (await db.execute(
        select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.seq)
    )).scalars().all()
    if not chunks:
        raise ValueError("文档尚未分块，请先解析")

    created: list[Question] = []

    # Split chunks into batches that fit token budget
    batch: list[str] = []
    batch_chars = 0
    for c in chunks:
        if batch and batch_chars + len(c.content) > _MAX_CHARS_PER_BATCH:
            created.extend(await _generate_batch(db, doc, batch))
            batch, batch_chars = [], 0
        batch.append(c.content)
        batch_chars += len(c.content)
    if batch:
        created.extend(await _generate_batch(db, doc, batch))

    # Trim to requested count
    result = created[:count]
    logger.info("Generated %d questions for doc %s", len(result), document_id)
    return result


async def _generate_batch(db: AsyncSession, doc: Document, chunks: list[str]) -> list[Question]:
    src = "\n\n---\n\n".join(chunks)
    prompt = f"""根据下面的学习资料生成 {max(3, min(6, len(chunks) * 2))} 道练习题。

资料《{doc.title}》节选：
{src[:9000]}

请输出 JSON 数组（不要任何多余文字），每项：
{{"type": "choice"|"fill", "question": "题目", "options": ["选项A","选项B","选项C","选项D","选项E","选项F"] | [], "answer": "正确答案", "explanation": "解析（引用资料内容）"}}
要求：
- 只生成客观题（选择题 + 填空题），不要生成简答题
- 尽量多出选择题；题目和答案必须严格基于资料内容
- 选择题必须给出恰好 6 个选项（选项A-F），答案必须唯一明确，且与其中一个选项完全一致
- 填空题答案必须简短、唯一、无歧义，不超过 20 字
- options 仅选择题有，填空题为空数组"""

    adapter = api_client.get_adapter(settings.default_model)
    resp = await adapter.chat_completion(
        [{"role": "user", "content": prompt}],
        AdapterConfig(temperature=0.6, max_tokens=3000),
    )
    data = _parse_array(resp.content)

    questions = []
    for q in data[:8]:
        qtype = q.get("type", "choice")
        if qtype not in ("choice", "fill"):
            continue  # 只保留客观题，简答题直接丢弃
        questions.append(Question(
            document_id=doc.id,
            qtype=qtype,
            question=str(q.get("question", "")).strip(),
            options=json.dumps(q.get("options") or [], ensure_ascii=False),
            answer=str(q.get("answer", "")).strip(),
            explanation=str(q.get("explanation", "")).strip(),
            source_text=src[:500],
        ))
    db.add_all(questions)
    await db.commit()
    return questions


def _parse_array(text: str) -> list[dict]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return []


def _parse_obj(text: str) -> dict:
    """从 LLM 返回里提取一个 JSON 对象；失败返回 {}。"""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return {}


# ---------------------------------------------------------------- grading

_ANSWER_KEYWORDS = re.compile(r"[\w一-鿿]+")
_STOP_CHARS = {"的", "了", "是", "在", "和", "与", "及", "或", "一个", "这个", "那个", "我们", "你们", "他们", "等", "之", "对", "把", "被", "让", "中", "上", "下", "也", "都", "就", "很", "与"}


def _keywords(text: str) -> set[str]:
    words = _ANSWER_KEYWORDS.findall(text)
    return {w for w in words if w not in _STOP_CHARS and len(w) > 1}


def grade_choice(options: list[str], answer: str, user_answer: str) -> bool:
    """选择题判分：支持选项全文 / 字母(A-D) / "A. 选项" 三种作答形式。

    注意：单个字母可能是合法选项原文（如答案就是 "n"），所以字母编号路径
    匹配失败时必须回退到全文匹配，避免把字母选项误判成编号。
    """
    user_answer = (user_answer or "").strip()
    picked = user_answer.upper()
    if len(picked) == 1 and picked.isalpha() and options:
        idx = ord(picked) - ord("A")
        if 0 <= idx < len(options) and options[idx].strip() == answer.strip():
            return True
    if user_answer == answer.strip():
        return True
    if len(picked) >= 2 and picked[0].isalpha() and picked[1] in (".", "、", " "):
        idx = ord(picked[0]) - ord("A")
        if 0 <= idx < len(options) and options[idx].strip() == answer.strip():
            return True
    return False


async def grade(db: AsyncSession, question_id: str, user_answer: str) -> dict:
    """Grade an answer. Choice: exact option match. Fill/Essay: keyword coverage."""
    q = await db.get(Question, question_id)
    if not q:
        raise ValueError("题目不存在")

    user_answer = (user_answer or "").strip()

    if q.qtype == "choice":
        try:
            options = json.loads(q.options or "[]")
        except json.JSONDecodeError:
            options = []
        correct = grade_choice(options, q.answer, user_answer)
        comment = ""
    else:
        # 填空/简答：AI 阅卷判断（失败回退关键词判分）
        ai = await _ai_grade(q, user_answer)
        if ai is not None:
            correct = ai["correct"]
            comment = ai.get("comment", "")
        else:
            correct = _grade_text(q.answer, user_answer)
            comment = ""

    db.add(QuizRecord(question_id=question_id, user_answer=user_answer, correct=correct))
    await db.commit()
    return {"correct": correct, "answer": q.answer, "explanation": q.explanation, "comment": comment}


def _grade_text(correct_answer: str, user_answer: str) -> bool:
    """Strict-enough keyword coverage check (from KnowAll US-04)."""
    ans_kw = _keywords(correct_answer)
    if not ans_kw or len(user_answer) < 4:
        return False
    user_kw = _keywords(user_answer)
    if not user_kw:
        return False
    overlap = ans_kw & user_kw
    # require ≥60% of the key answer keywords present
    return len(overlap) / len(ans_kw) >= 0.6


async def _ai_grade(q: Question, user_answer: str) -> dict | None:
    """LLM 阅卷：判断填空/简答答案对错并给出点评。

    返回 {"correct": bool, "comment": str}；失败（含用户作答太短）返回 None，
    由调用方回退到关键词判分。
    """
    if len(user_answer) < 4:
        return None
    prompt = f"""你是阅卷老师，判断学生的答案是否正确。
【题目】{q.question}
【参考答案】{q.answer}
【学生的回答】{user_answer}

只输出一个 JSON 对象（不要任何多余文字）：
{{"correct": true 或 false, "comment": "一句话点评（答对则肯定；答错指出错在哪、怎么改，20字内）"}}"""
    try:
        adapter = api_client.get_adapter(settings.default_model)
        resp = await adapter.chat_completion(
            [{"role": "user", "content": prompt}],
            AdapterConfig(temperature=0.2, max_tokens=200),
        )
        data = _parse_obj(resp.content)
        if "correct" in data:
            return {"correct": bool(data["correct"]), "comment": str(data.get("comment", ""))}
    except Exception as e:
        logger.warning("AI 阅卷失败，回退关键词判分: %s", e)
    return None


async def quiz_stats(db: AsyncSession, document_id: str | None = None) -> dict:
    """Aggregate quiz stats for a document (or all)."""
    stmt = select(QuizRecord, Question).join(Question, QuizRecord.question_id == Question.id)
    if document_id:
        stmt = stmt.where(Question.document_id == document_id)
    rows = (await db.execute(stmt)).all()
    total = len(rows)
    correct = sum(1 for r, _ in rows if r.correct)
    return {"total": total, "correct": correct, "accuracy": round(correct / total, 3) if total else 0.0}


# ---------------------------------------------------------------- 题目管理（弃用 / 错题本）

async def get_question(db: AsyncSession, question_id: str) -> Question | None:
    return await db.get(Question, question_id)


async def set_question_discarded(db: AsyncSession, question_id: str, discarded: bool) -> Question:
    """弃用（软删除，从默认列表隐藏）或恢复。"""
    q = await db.get(Question, question_id)
    if not q:
        raise ValueError("题目不存在")
    q.discarded = discarded
    await db.commit()
    await db.refresh(q)
    return q


async def set_question_mistake(db: AsyncSession, question_id: str, in_book: bool) -> Question:
    """加入 / 移出错题本。"""
    q = await db.get(Question, question_id)
    if not q:
        raise ValueError("题目不存在")
    q.in_mistake_book = in_book
    await db.commit()
    await db.refresh(q)
    return q


async def list_questions(db: AsyncSession, document_id: str | None = None,
                         include_discarded: bool = False,
                         mistake_book: bool = False) -> list[Question]:
    """列出题目。默认排除已弃用；mistake_book=True 只列错题本。"""
    stmt = select(Question)
    if not include_discarded:
        stmt = stmt.where(Question.discarded == False)  # noqa: E712
    if mistake_book:
        stmt = stmt.where(Question.in_mistake_book == True)  # noqa: E712
    if document_id:
        stmt = stmt.where(Question.document_id == document_id)
    stmt = stmt.order_by(Question.created_at)
    return (await db.execute(stmt)).scalars().all()
