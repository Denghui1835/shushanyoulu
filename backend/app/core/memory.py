"""FSRS 间隔复习 + 闪卡管理."""
import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.api_scheduler import api_client
from app.core.api_scheduler.adapters.base import AdapterConfig
from app.core.parsing import estimate_tokens
from app.models import Document, Chunk, Flashcard

logger = logging.getLogger("yuanqi.memory")

# FSRS v4 default weights (small set, adequate for MVP)
DEFAULT_W = [0.4, 0.6, 2.4, 5.8, 4.93, 0.94, 0.86, 0.01, 1.49, 0.14, 0.94, 2.18, 0.05, 0.34, 1.26, 0.29, 2.61]
_W = DEFAULT_W


def _decay(d: float) -> float:
    return float(d) * 0.9 + _W[16] if d >= 0 else float(d) * 0.9 + _W[16]


def _d(d: float, elapsed_days: float) -> float:
    return _W[15] * pow(elapsed_days, -_W[16])


async def generate_flashcards(db: AsyncSession, document_id: str, count: int = 15) -> list[Flashcard]:
    """Generate flashcards for a document (LLM)."""
    doc = await db.get(Document, document_id)
    if not doc:
        raise ValueError("文档不存在")
    chunks = (await db.execute(
        select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.seq)
    )).scalars().all()
    if not chunks:
        raise ValueError("文档尚未分块")

    src = "\n\n---\n\n".join(c.content for c in chunks)
    # token-budget truncation
    while estimate_tokens(src) > 6000 and len(src) > 2000:
        src = src[:int(len(src) * 0.8)]

    prompt = f"""根据资料生成 {min(count, 15)} 张记忆闪卡。

资料《{doc.title}》：
{src}

输出 JSON 数组（不要多余文字），每项：
{{"front": "正面：知识点/问题", "back": "背面：简洁答案（关键概念或数字）"}}
要求：每张卡片一个独立知识点，正面提问、背面作答，中文字数各不超过 60 字。"""

    adapter = api_client.get_adapter(settings.default_model)
    resp = await adapter.chat_completion(
        [{"role": "user", "content": prompt}],
        AdapterConfig(temperature=0.6, max_tokens=3000),
    )
    data = _parse_array(resp.content)

    cards = []
    for c in data[:count]:
        front = str(c.get("front", "")).strip()
        back = str(c.get("back", "")).strip()
        if not front or not back:
            continue
        cards.append(Flashcard(document_id=doc.id, front=front, back=back))
    db.add_all(cards)
    await db.commit()
    logger.info("Generated %d flashcards for doc %s", len(cards), document_id)
    return cards


def _parse_array(text: str) -> list[dict]:
    import re
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return []


# ---------------------------------------------------------------- review scheduling

def _days_since(dt: datetime | None) -> float:
    if not dt:
        return 0.0
    return max(0.0, (datetime.now() - dt).total_seconds() / 86400.0)


def schedule(card: Flashcard, rating: int) -> dict:
    """FSRS-style scheduling. rating: 1=再次 2=困难 3=良好 4=简单."""
    w = _W
    r = rating
    now = datetime.now()

    if card.reps == 0:  # first review
        stability = 1.0
        difficulty = 2.5 if r >= 3 else 4.0
        if r == 1:
            interval_days = 1
        elif r == 2:
            interval_days = 3
        else:
            interval_days = 5 if r == 3 else 10
        card.status = "review"
    else:
        stability = card.stability or 1.0
        difficulty = card.difficulty or 2.5
        elapsed = _days_since(card.last_reviewed_at)
        hard_penalty = 1.3 if r == 1 else 1.0
        stability *= (0.95 + 0.25 * r) / hard_penalty
        difficulty = min(10, max(1, difficulty + (0.3 if r <= 2 else -0.2)))
        if r == 1:
            interval_days = max(1, int(elapsed * 0.5))
            card.lapses += 1
        elif r == 2:
            interval_days = max(2, int(stability * 0.6))
        elif r == 3:
            interval_days = int(stability)
        else:
            interval_days = int(stability * 1.6)
        card.status = "review"

    card.reps += 1
    card.stability = round(stability, 3)
    card.difficulty = round(difficulty, 3)
    card.due_at = now + timedelta(days=interval_days)
    card.last_reviewed_at = now
    return {"interval_days": interval_days, "stability": card.stability, "difficulty": card.difficulty}


async def review(db: AsyncSession, card_id: str, rating: int) -> dict:
    """Review a flashcard with the given rating and persist the schedule."""
    card = await db.get(Flashcard, card_id)
    if not card:
        raise ValueError("闪卡不存在")
    result = schedule(card, rating)
    await db.commit()
    return result


async def due_count(db: AsyncSession) -> int:
    now = datetime.now()
    return int((await db.execute(
        select(func.count()).select_from(Flashcard).where(
            Flashcard.due_at.is_not(None), Flashcard.due_at <= now,
            Flashcard.discarded == False,  # noqa: E712
        )
    )).scalar() or 0)


# ---------------------------------------------------------------- 闪卡管理（弃用 / 恢复）

async def set_flashcard_discarded(db: AsyncSession, card_id: str, discarded: bool) -> Flashcard:
    """弃用闪卡（软删除，从列表隐藏，可恢复）。"""
    card = await db.get(Flashcard, card_id)
    if not card:
        raise ValueError("闪卡不存在")
    card.discarded = discarded
    await db.commit()
    await db.refresh(card)
    return card
