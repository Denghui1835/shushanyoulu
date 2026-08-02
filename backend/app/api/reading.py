"""阅读功能 API：阅读单元内容、批注 CRUD、总结生成与查询."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.reading_content import get_reading_units
from app.core.summarize import generate_summary
from app.models import Document, Annotation, DocSummary

router = APIRouter(prefix="/api/reading", tags=["reading"])


async def _get_doc(db: AsyncSession, document_id: str) -> Document:
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    return doc


# ---------------------------------------------------------------- 阅读单元

@router.get("/{document_id}/content")
async def get_content(document_id: str, db: AsyncSession = Depends(get_db)):
    doc = await _get_doc(db, document_id)
    units = await get_reading_units(db, doc)
    return {
        "document_id": doc.id,
        "title": doc.title,
        "content_type": doc.content_type,
        "units": units,
    }


# ---------------------------------------------------------------- 批注

class AnnotationIn(BaseModel):
    unit_type: str = "chunk"          # page / chunk
    unit_index: int = 0
    start_offset: int = 0
    end_offset: int = 0
    selected_text: str = ""
    content: str = ""


class AnnotationUpdate(BaseModel):
    content: str | None = None


@router.get("/{document_id}/annotations")
async def list_annotations(document_id: str, db: AsyncSession = Depends(get_db)):
    await _get_doc(db, document_id)
    rows = (await db.execute(
        select(Annotation).where(Annotation.document_id == document_id).order_by(Annotation.created_at)
    )).scalars().all()
    return [_serialize_ann(a) for a in rows]


@router.post("/{document_id}/annotations")
async def create_annotation(document_id: str, data: AnnotationIn, db: AsyncSession = Depends(get_db)):
    await _get_doc(db, document_id)
    if data.start_offset < 0 or data.end_offset < data.start_offset:
        raise HTTPException(status_code=400, detail="批注区间无效")
    ann = Annotation(
        document_id=document_id,
        unit_type=data.unit_type if data.unit_type in ("page", "chunk") else "chunk",
        unit_index=data.unit_index,
        start_offset=data.start_offset,
        end_offset=data.end_offset,
        selected_text=data.selected_text,
        content=data.content,
    )
    db.add(ann)
    await db.commit()
    await db.refresh(ann)
    return _serialize_ann(ann)


@router.put("/annotations/{annotation_id}")
async def update_annotation(annotation_id: str, data: AnnotationUpdate, db: AsyncSession = Depends(get_db)):
    ann = await db.get(Annotation, annotation_id)
    if not ann:
        raise HTTPException(status_code=404, detail="批注不存在")
    if data.content is not None:
        ann.content = data.content
    await db.commit()
    return _serialize_ann(ann)


@router.delete("/annotations/{annotation_id}")
async def delete_annotation(annotation_id: str, db: AsyncSession = Depends(get_db)):
    ann = await db.get(Annotation, annotation_id)
    if not ann:
        raise HTTPException(status_code=404, detail="批注不存在")
    await db.delete(ann)
    await db.commit()
    return {"ok": True}


def _serialize_ann(a: Annotation) -> dict:
    return {
        "id": a.id, "document_id": a.document_id, "unit_type": a.unit_type,
        "unit_index": a.unit_index, "start_offset": a.start_offset,
        "end_offset": a.end_offset, "selected_text": a.selected_text,
        "content": a.content, "created_at": a.created_at.isoformat(),
        "updated_at": a.updated_at.isoformat(),
    }


# ---------------------------------------------------------------- 总结

class SummarizeIn(BaseModel):
    scope: str = "overall"            # overall / page / story / concept
    unit_index: int | None = None


@router.post("/{document_id}/summarize")
async def summarize(document_id: str, data: SummarizeIn, db: AsyncSession = Depends(get_db)):
    doc = await _get_doc(db, document_id)
    if data.scope not in ("overall", "page", "story", "concept"):
        raise HTTPException(status_code=400, detail="scope 须为 overall/page/story/concept")
    if data.scope == "page" and data.unit_index is None:
        raise HTTPException(status_code=400, detail="页级总结需要 unit_index")
    summary = await generate_summary(db, doc, scope=data.scope,
                                     unit_index=None if data.scope in ("story", "concept") else data.unit_index)
    return _serialize_summary(summary)


@router.get("/{document_id}/summaries")
async def list_summaries(document_id: str, db: AsyncSession = Depends(get_db)):
    await _get_doc(db, document_id)
    rows = (await db.execute(
        select(DocSummary).where(DocSummary.document_id == document_id).order_by(DocSummary.updated_at)
    )).scalars().all()
    return [_serialize_summary(s) for s in rows]


def _serialize_summary(s: DocSummary) -> dict:
    return {
        "id": s.id, "document_id": s.document_id, "scope": s.scope,
        "unit_index": s.unit_index, "content": s.content, "status": s.status,
        "error": s.error, "updated_at": s.updated_at.isoformat(),
    }
