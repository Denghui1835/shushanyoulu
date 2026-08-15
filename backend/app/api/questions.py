"""题目 API — 生成、列表、评分、统计、管理（弃用/恢复、错题本）."""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.quiz import (
    generate_questions, grade, quiz_stats, set_question_discarded, set_question_mistake,
    list_questions as list_questions_core,
)
from app.core.mock_exam import build_mock_exam, grade_mock_exam
from app.models import Question, QuizRecord, Document, MockRecord

router = APIRouter(prefix="/api/questions", tags=["questions"])


class GradeIn(BaseModel):
    user_answer: str


class MockGradeIn(BaseModel):
    answers: dict[str, str]
    subject: str = "python"   # python / c


# ---------------------------------------------------------------- 全真模拟（须在 /{document_id} 之前定义）

@router.get("/mock")
async def mock_exam(subject: str = "python", db: AsyncSession = Depends(get_db)):
    """全真模拟考试卷：严格仿 NCRE-2（python/c 两种科目，120 分钟、40 选择 + 60 操作）。"""
    return await build_mock_exam(db, subject)


@router.post("/mock/grade")
async def mock_grade(data: MockGradeIn, db: AsyncSession = Depends(get_db)):
    """交卷判分：返回成绩单（总分/部分分/合格/逐题解析）。"""
    try:
        return await grade_mock_exam(db, data.answers, data.subject)
    except Exception as e:
        import logging
        logging.getLogger("yuanqi.api.questions").exception("mock grade failed")
        raise HTTPException(status_code=500, detail=f"判分失败：{e}")


@router.get("/mock/history")
async def mock_history(limit: int = 50, db: AsyncSession = Depends(get_db)):
    """模拟成绩历史：按时间倒序，供成绩单回看与进步曲线。"""
    rows = (await db.execute(
        select(MockRecord).where(MockRecord.user_id == "local_user")
        .order_by(MockRecord.created_at.desc()).limit(min(limit, 200))
    )).scalars().all()
    return {
        "items": [{
            "id": r.id,
            "subject": r.subject,
            "total": r.total,
            "max_score": r.max_score,
            "passed": r.passed,
            "section_scores": json.loads(r.section_scores or "[]"),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in rows],
    }


# ---------------------------------------------------------------- 错题本（须在 /{document_id} 之前定义）

@router.get("/mistakes")
async def list_mistakes(db: AsyncSession = Depends(get_db)):
    """错题本：所有已加入错题本的题目（含文档名）。"""
    qs = await list_questions_core(db, mistake_book=True)
    doc_ids = {q.document_id for q in qs}
    docs = (await db.execute(select(Document).where(Document.id.in_(doc_ids)))).scalars().all()
    title_map = {d.id: d.title for d in docs}
    return {"count": len(qs), "questions": [_serialize(q, title_map.get(q.document_id, "")) for q in qs]}


# ---------------------------------------------------------------- 文档维度

@router.post("/{document_id}/generate")
async def create_questions(document_id: str, count: int = 8, db: AsyncSession = Depends(get_db)):
    try:
        qs = await generate_questions(db, document_id, count)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"count": len(qs), "questions": [_serialize(q) for q in qs]}


@router.get("/{document_id}")
async def list_questions(document_id: str, include_discarded: bool = False,
                         mistake_book: bool = False, db: AsyncSession = Depends(get_db)):
    qs = await list_questions_core(db, document_id, include_discarded=include_discarded,
                                   mistake_book=mistake_book)
    return {"count": len(qs), "questions": [_serialize(q) for q in qs]}


@router.get("/{document_id}/stats")
async def stats(document_id: str, db: AsyncSession = Depends(get_db)):
    return await quiz_stats(db, document_id)


# ---------------------------------------------------------------- 题目维度（评分 / 管理）

@router.post("/{question_id}/grade")
async def grade_question(question_id: str, data: GradeIn, db: AsyncSession = Depends(get_db)):
    try:
        result = await grade(db, question_id, data.user_answer)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return result


@router.post("/{question_id}/discard")
async def discard_question(question_id: str, db: AsyncSession = Depends(get_db)):
    """弃用题目（软删除，从默认列表隐藏，可恢复）。"""
    try:
        q = await set_question_discarded(db, question_id, True)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _serialize(q)


@router.post("/{question_id}/restore")
async def restore_question(question_id: str, db: AsyncSession = Depends(get_db)):
    """恢复被弃用的题目。"""
    try:
        q = await set_question_discarded(db, question_id, False)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _serialize(q)


@router.post("/{question_id}/mistake-book")
async def add_to_mistake_book(question_id: str, db: AsyncSession = Depends(get_db)):
    """加入错题本。"""
    try:
        q = await set_question_mistake(db, question_id, True)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _serialize(q)


@router.delete("/{question_id}/mistake-book")
async def remove_from_mistake_book(question_id: str, db: AsyncSession = Depends(get_db)):
    """移出错题本。"""
    try:
        q = await set_question_mistake(db, question_id, False)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _serialize(q)


def _serialize(q: Question, doc_title: str = "") -> dict:
    try:
        options = json.loads(q.options or "[]")
    except json.JSONDecodeError:
        options = []
    return {
        "id": q.id, "document_id": q.document_id, "qtype": q.qtype,
        "question": q.question, "options": options, "answer": q.answer,
        "explanation": q.explanation, "source_text": q.source_text[:200],
        "discarded": bool(q.discarded), "in_mistake_book": bool(q.in_mistake_book),
        "doc_title": doc_title,
    }
