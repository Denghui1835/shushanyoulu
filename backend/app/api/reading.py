"""阅读功能 API：阅读单元内容、批注 CRUD、总结生成与查询、PDF 自由绘制."""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.reading_content import get_reading_units
from app.core.summarize import generate_summary
from app.core.blank import get_blank_content
from app.models import Document, Annotation, DocSummary, Drawing

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
    # 按书配置：是否开启「关键词挖空」
    from app.models import Project
    project = await db.get(Project, doc.project_id) if doc.project_id else None
    blank_enabled = bool(project.blank_enabled) if project else False
    return {
        "document_id": doc.id,
        "title": doc.title,
        "content_type": doc.content_type,
        "blank_enabled": blank_enabled,
        "units": units,
    }


# ---------------------------------------------------------------- 关键词挖空

@router.get("/{document_id}/blank")
async def blank_content(document_id: str, unit_index: int = 0, db: AsyncSession = Depends(get_db)):
    """关键词挖空背诵：某阅读单元的关键词 + 出现位置（前端替换为可点击空白）。"""
    doc = await _get_doc(db, document_id)
    try:
        data = await get_blank_content(db, doc, unit_index)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("挖空内容生成失败 doc=%s unit=%s", document_id, unit_index)
        raise HTTPException(status_code=500, detail=f"生成失败：{str(e)[:200]}")
    return data


# ---------------------------------------------------------------- PDF 自由绘制批注

class DrawingIn(BaseModel):
    strokes: list = []   # 每项 {id,tool,color,size,points:[{x,y}]}，坐标 0-1 归一化


def _serialize_drawing(d: Drawing) -> dict:
    try:
        strokes = json.loads(d.strokes or "[]")
    except Exception:
        strokes = []
    return {"id": d.id, "unit_index": d.unit_index, "strokes": strokes,
            "updated_at": d.updated_at.isoformat()}


@router.get("/{document_id}/drawings")
async def list_drawings(document_id: str, db: AsyncSession = Depends(get_db)):
    """全部页的绘制批注（与文本批注共存）。"""
    await _get_doc(db, document_id)
    rows = (await db.execute(
        select(Drawing).where(Drawing.document_id == document_id).order_by(Drawing.unit_index)
    )).scalars().all()
    return {"count": len(rows), "items": [_serialize_drawing(d) for d in rows]}


@router.post("/{document_id}/drawings/{unit_index}")
async def save_drawings(document_id: str, unit_index: int, data: DrawingIn,
                        db: AsyncSession = Depends(get_db)):
    """保存某页的笔迹（整体覆盖，幂等）。"""
    await _get_doc(db, document_id)
    row = (await db.execute(
        select(Drawing).where(Drawing.document_id == document_id,
                              Drawing.unit_index == unit_index)
    )).scalars().first()
    strokes = json.dumps(data.strokes or [], ensure_ascii=False)
    if row:
        row.strokes = strokes
    else:
        db.add(Drawing(document_id=document_id, unit_index=unit_index, strokes=strokes))
    await db.commit()
    saved = (await db.execute(
        select(Drawing).where(Drawing.document_id == document_id,
                              Drawing.unit_index == unit_index)
    )).scalars().first()
    return _serialize_drawing(saved)


@router.delete("/{document_id}/drawings/{unit_index}")
async def clear_drawings(document_id: str, unit_index: int, db: AsyncSession = Depends(get_db)):
    """清空某页笔迹。"""
    await _get_doc(db, document_id)
    row = (await db.execute(
        select(Drawing).where(Drawing.document_id == document_id,
                              Drawing.unit_index == unit_index)
    )).scalars().first()
    if row:
        await db.delete(row)
        await db.commit()
    return {"ok": True}


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
