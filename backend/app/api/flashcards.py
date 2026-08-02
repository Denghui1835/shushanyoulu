"""闪卡 API — 生成、复习、待复习列表."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.memory import generate_flashcards, review, due_count
from app.models import Flashcard

router = APIRouter(prefix="/api/flashcards", tags=["flashcards"])


@router.post("/{document_id}/generate")
async def create_flashcards(document_id: str, count: int = 15, db: AsyncSession = Depends(get_db)):
    try:
        cards = await generate_flashcards(db, document_id, count)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"count": len(cards), "flashcards": [_serialize(c) for c in cards]}


@router.get("/due")
async def due_flashcards(limit: int = 20, db: AsyncSession = Depends(get_db)):
    now = datetime.now()
    cards = (await db.execute(
        select(Flashcard).where(Flashcard.due_at.is_not(None), Flashcard.due_at <= now)
        .order_by(Flashcard.due_at).limit(limit)
    )).scalars().all()
    return {"count": len(cards), "due_total": await due_count(db),
            "flashcards": [_serialize(c) for c in cards]}


@router.get("/{document_id}")
async def list_flashcards(document_id: str, db: AsyncSession = Depends(get_db)):
    cards = (await db.execute(
        select(Flashcard).where(Flashcard.document_id == document_id).order_by(Flashcard.created_at)
    )).scalars().all()
    return {"count": len(cards), "flashcards": [_serialize(c) for c in cards]}


class ReviewIn(BaseModel):
    rating: int  # 1=再次 2=困难 3=良好 4=简单


@router.post("/{card_id}/review")
async def review_card(card_id: str, data: ReviewIn, db: AsyncSession = Depends(get_db)):
    if data.rating not in (1, 2, 3, 4):
        raise HTTPException(status_code=400, detail="rating 须为 1-4")
    try:
        result = await review(db, card_id, data.rating)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return result


def _serialize(c: Flashcard) -> dict:
    return {
        "id": c.id, "document_id": c.document_id, "front": c.front, "back": c.back,
        "status": c.status,
        "due_at": c.due_at.isoformat() if c.due_at else None,
        "reps": c.reps, "lapses": c.lapses,
    }
