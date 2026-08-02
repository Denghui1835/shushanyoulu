"""知识树 API."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.knowledge import generate_knowledge_tree
from app.models import KnowledgePoint, Document

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.post("/{document_id}/generate")
async def generate_tree(document_id: str, db: AsyncSession = Depends(get_db)):
    try:
        points = await generate_knowledge_tree(db, document_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"count": len(points), "tree": _build_tree(points)}


@router.get("/{document_id}")
async def get_tree(document_id: str, db: AsyncSession = Depends(get_db)):
    points = (await db.execute(
        select(KnowledgePoint).where(KnowledgePoint.document_id == document_id).order_by(KnowledgePoint.order_index)
    )).scalars().all()
    return {"count": len(points), "tree": _build_tree(points)}


def _build_tree(points: list[KnowledgePoint]) -> list[dict]:
    by_parent: dict[str, list] = {}
    for p in points:
        by_parent.setdefault(p.parent_id or "", []).append(p)
    nodes: dict[str, dict] = {}
    for p in points:
        nodes[p.id] = {"id": p.id, "title": p.title, "summary": p.summary, "children": []}
    for p in points:
        node = nodes[p.id]
        if p.parent_id and p.parent_id in nodes:
            nodes[p.parent_id]["children"].append(node)
    return by_parent.get("", []) and [nodes[p.id] for p in by_parent[""]] or []
