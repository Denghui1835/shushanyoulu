"""题目 API — 生成、列表、评分、统计."""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.quiz import generate_questions, grade, quiz_stats
from app.models import Question, QuizRecord, Document

router = APIRouter(prefix="/api/questions", tags=["questions"])


class GradeIn(BaseModel):
    user_answer: str


@router.post("/{document_id}/generate")
async def create_questions(document_id: str, count: int = 8, db: AsyncSession = Depends(get_db)):
    try:
        qs = await generate_questions(db, document_id, count)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"count": len(qs), "questions": [_serialize(q) for q in qs]}


@router.get("/{document_id}")
async def list_questions(document_id: str, db: AsyncSession = Depends(get_db)):
    qs = (await db.execute(
        select(Question).where(Question.document_id == document_id).order_by(Question.created_at)
    )).scalars().all()
    return {"count": len(qs), "questions": [_serialize(q) for q in qs]}


@router.get("/{document_id}/stats")
async def stats(document_id: str, db: AsyncSession = Depends(get_db)):
    return await quiz_stats(db, document_id)


@router.post("/{question_id}/grade")
async def grade_question(question_id: str, data: GradeIn, db: AsyncSession = Depends(get_db)):
    try:
        result = await grade(db, question_id, data.user_answer)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return result


def _serialize(q: Question) -> dict:
    try:
        options = json.loads(q.options or "[]")
    except json.JSONDecodeError:
        options = []
    return {
        "id": q.id, "document_id": q.document_id, "qtype": q.qtype,
        "question": q.question, "options": options, "answer": q.answer,
        "explanation": q.explanation, "source_text": q.source_text[:200],
    }
