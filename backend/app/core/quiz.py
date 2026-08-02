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
{{"type": "choice"|"fill"|"essay", "question": "题目", "options": ["选项A","选项B","选项C","选项D"] | [], "answer": "正确答案", "explanation": "解析（引用资料内容）"}}
要求：
- 至少包含 2 道选择题，题目和答案必须严格基于资料内容
- 填空题答案不超过 20 字；简答题答案 1-3 句
- options 仅选择题有，其余为空数组"""

    adapter = api_client.get_adapter(settings.default_model)
    resp = await adapter.chat_completion(
        [{"role": "user", "content": prompt}],
        AdapterConfig(temperature=0.6, max_tokens=3000),
    )
    data = _parse_array(resp.content)

    questions = []
    for q in data[:8]:
        qtype = q.get("type", "choice")
        if qtype not in ("choice", "fill", "essay"):
            qtype = "choice"
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


# ---------------------------------------------------------------- grading

_ANSWER_KEYWORDS = re.compile(r"[\w一-鿿]+")
_STOP_CHARS = {"的", "了", "是", "在", "和", "与", "及", "或", "一个", "这个", "那个", "我们", "你们", "他们", "等", "之", "对", "把", "被", "让", "中", "上", "下", "也", "都", "就", "很", "与"}


def _keywords(text: str) -> set[str]:
    words = _ANSWER_KEYWORDS.findall(text)
    return {w for w in words if w not in _STOP_CHARS and len(w) > 1}


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
        correct = False
        picked = user_answer.strip().upper()
        # accept letter (A/B/C/D) or full option text
        if len(picked) == 1 and picked.isalpha() and options:
            idx = ord(picked) - ord("A")
            correct = 0 <= idx < len(options) and options[idx].strip() == q.answer.strip()
        else:
            correct = user_answer == q.answer.strip()
            # also match letter + text like "A. xxx"
            if not correct and len(picked) >= 2 and picked[0].isalpha() and picked[1] in (".", "、", " "):
                idx = ord(picked[0].upper()) - ord("A")
                correct = 0 <= idx < len(options) and options[idx].strip() == q.answer.strip()
    else:
        correct = _grade_text(q.answer, user_answer)

    db.add(QuizRecord(question_id=question_id, user_answer=user_answer, correct=correct))
    await db.commit()
    return {"correct": correct, "answer": q.answer, "explanation": q.explanation}


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


async def quiz_stats(db: AsyncSession, document_id: str | None = None) -> dict:
    """Aggregate quiz stats for a document (or all)."""
    stmt = select(QuizRecord, Question).join(Question, QuizRecord.question_id == Question.id)
    if document_id:
        stmt = stmt.where(Question.document_id == document_id)
    rows = (await db.execute(stmt)).all()
    total = len(rows)
    correct = sum(1 for r, _ in rows if r.correct)
    return {"total": total, "correct": correct, "accuracy": round(correct / total, 3) if total else 0.0}
