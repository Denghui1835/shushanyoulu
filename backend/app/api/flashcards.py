"""闪卡 API — 生成、复习、待复习列表、弃用/恢复/删除."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.memory import generate_flashcards, review, due_count, set_flashcard_discarded
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
        select(Flashcard).where(
            Flashcard.due_at.is_not(None), Flashcard.due_at <= now,
            Flashcard.discarded == False,  # noqa: E712
        ).order_by(Flashcard.due_at).limit(limit)
    )).scalars().all()
    return {"count": len(cards), "due_total": await due_count(db),
            "flashcards": [_serialize(c) for c in cards]}


@router.get("/{document_id}")
async def list_flashcards(document_id: str, include_discarded: bool = False,
                          db: AsyncSession = Depends(get_db)):
    stmt = select(Flashcard).where(Flashcard.document_id == document_id)
    if not include_discarded:
        stmt = stmt.where(Flashcard.discarded == False)  # noqa: E712
    cards = (await db.execute(stmt.order_by(Flashcard.created_at))).scalars().all()
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


# ---------------------------------------------------------------- 管理：弃用 / 恢复 / 删除

@router.post("/{card_id}/discard")
async def discard_flashcard(card_id: str, db: AsyncSession = Depends(get_db)):
    """弃用闪卡（软删除，可恢复）。"""
    try:
        card = await set_flashcard_discarded(db, card_id, True)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _serialize(card)


@router.post("/{card_id}/restore")
async def restore_flashcard(card_id: str, db: AsyncSession = Depends(get_db)):
    """恢复被弃用的闪卡。"""
    try:
        card = await set_flashcard_discarded(db, card_id, False)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _serialize(card)


@router.delete("/{card_id}")
async def delete_flashcard(card_id: str, db: AsyncSession = Depends(get_db)):
    """彻底删除闪卡。"""
    card = await db.get(Flashcard, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="闪卡不存在")
    await db.execute(delete(Flashcard).where(Flashcard.id == card_id))
    await db.commit()
    return {"ok": True}


def _serialize(c: Flashcard) -> dict:
    return {
        "id": c.id, "document_id": c.document_id, "front": c.front, "back": c.back,
        "status": c.status,
        "due_at": c.due_at.isoformat() if c.due_at else None,
        "reps": c.reps, "lapses": c.lapses, "discarded": bool(c.discarded),
    }
