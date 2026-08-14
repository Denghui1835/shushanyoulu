"""看板 API：列 CRUD / 卡片 CRUD / 拖拽移动 / 整板初始化。

KanbanCard 可独立存在或关联 PlanTask（plan_task_id 可选）。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Project, PlanTask
from app.models.kanban import KanbanColumn, KanbanCard

logger = logging.getLogger("yuanqi.api.kanban")
router = APIRouter(prefix="/api/projects", tags=["kanban"])

PRIORITY_LABELS = {"high": "高", "medium": "中", "low": "低"}


# ── 辅助 ──

async def _get_project(db: AsyncSession, project_id: str) -> Project:
    proj = await db.get(Project, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在")
    return proj


def _card_out(c: KanbanCard) -> dict:
    return {
        "id": c.id, "column_id": c.column_id, "title": c.title,
        "description": c.description, "priority": c.priority,
        "due_date": c.due_date, "assignee": c.assignee,
        "sort_order": c.sort_order, "plan_task_id": c.plan_task_id,
        "created_at": c.created_at.isoformat(),
    }


def _col_out(c: KanbanColumn) -> dict:
    return {"id": c.id, "title": c.title, "sort_order": c.sort_order, "is_default": c.is_default}


DEFAULT_COLS = [
    {"title": "待办", "sort_order": 0, "is_default": True},
    {"title": "进行中", "sort_order": 1, "is_default": True},
    {"title": "已完成", "sort_order": 2, "is_default": True},
]


# ── GET 整板 ──

@router.get("/{project_id}/kanban")
async def get_kanban(project_id: str, db: AsyncSession = Depends(get_db)):
    """返回项目完整看板：开关状态 + 列 + 卡片。首次调用自动初始化默认三列。"""
    proj = await _get_project(db, project_id)

    # 若尚无列，初始化默认三列
    existing = (await db.execute(
        select(func.count(KanbanColumn.id)).where(KanbanColumn.project_id == project_id)
    )).scalar() or 0
    if existing == 0:
        for dc in DEFAULT_COLS:
            col = KanbanColumn(project_id=project_id, **dc)
            db.add(col)
        await db.commit()

    cols = list((await db.execute(
        select(KanbanColumn).where(KanbanColumn.project_id == project_id).order_by(KanbanColumn.sort_order)
    )).scalars())

    col_ids = [c.id for c in cols]
    cards = list((await db.execute(
        select(KanbanCard).where(KanbanCard.column_id.in_(col_ids)).order_by(KanbanCard.sort_order)
    )).scalars()) if col_ids else []

    return {
        "kanban_enabled": bool(getattr(proj, "kanban_enabled", False)),
        "columns": [_col_out(c) for c in cols],
        "cards": [_card_out(c) for c in cards],
    }


# ── 看板开关 ──

class KanbanToggleIn(BaseModel):
    enabled: bool


@router.put("/{project_id}/kanban/toggle")
async def toggle_kanban(project_id: str, data: KanbanToggleIn, db: AsyncSession = Depends(get_db)):
    """启用/关闭看板。关闭不删数据，重新开启即恢复。"""
    proj = await _get_project(db, project_id)
    proj.kanban_enabled = data.enabled  # type: ignore[attr-defined]
    await db.commit()
    return {"kanban_enabled": data.enabled}


# ── 列 CRUD ──

class ColIn(BaseModel):
    title: str


class ColReorderIn(BaseModel):
    column_ids: list[str]  # 新的顺序


@router.post("/{project_id}/kanban/columns")
async def create_column(project_id: str, data: ColIn, db: AsyncSession = Depends(get_db)):
    await _get_project(db, project_id)
    max_order = (await db.execute(
        select(func.coalesce(func.max(KanbanColumn.sort_order), -1)).where(
            KanbanColumn.project_id == project_id)
    )).scalar() or -1
    col = KanbanColumn(project_id=project_id, title=data.title, sort_order=max_order + 1)
    db.add(col)
    await db.commit()
    await db.refresh(col)
    return _col_out(col)


@router.put("/{project_id}/kanban/columns/{col_id}")
async def rename_column(project_id: str, col_id: str, data: ColIn, db: AsyncSession = Depends(get_db)):
    col = await db.get(KanbanColumn, col_id)
    if not col or col.project_id != project_id:
        raise HTTPException(status_code=404, detail="列不存在")
    if col.is_default and data.title != col.title:
        raise HTTPException(status_code=400, detail="默认列不可重命名")
    col.title = data.title
    await db.commit()
    return _col_out(col)


@router.delete("/{project_id}/kanban/columns/{col_id}")
async def delete_column(project_id: str, col_id: str, db: AsyncSession = Depends(get_db)):
    col = await db.get(KanbanColumn, col_id)
    if not col or col.project_id != project_id:
        raise HTTPException(status_code=404, detail="列不存在")
    if col.is_default:
        raise HTTPException(status_code=400, detail="默认列不可删除")
    await db.execute(delete(KanbanCard).where(KanbanCard.column_id == col_id))
    await db.delete(col)
    await db.commit()
    return {"ok": True}


@router.put("/{project_id}/kanban/columns/reorder")
async def reorder_columns(project_id: str, data: ColReorderIn, db: AsyncSession = Depends(get_db)):
    await _get_project(db, project_id)
    cols = (await db.execute(
        select(KanbanColumn).where(KanbanColumn.project_id == project_id)
    )).scalars().all()
    col_map = {c.id: c for c in cols}
    for i, cid in enumerate(data.column_ids):
        if cid in col_map:
            col_map[cid].sort_order = i
    await db.commit()
    return {"ok": True}


# ── 卡片 CRUD ──

class CardIn(BaseModel):
    column_id: str
    title: str
    description: str = ""
    priority: str = "medium"
    due_date: str | None = None
    assignee: str = ""


class CardMoveIn(BaseModel):
    column_id: str          # 目标列
    sort_order: int         # 目标位置
    above_id: str | None = None   # 插入到该卡片上方（可选，辅助前端）


class CardUpdateIn(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: str | None = None
    due_date: str | None = None
    assignee: str | None = None


@router.post("/{project_id}/kanban/cards")
async def create_card(project_id: str, data: CardIn, db: AsyncSession = Depends(get_db)):
    await _get_project(db, project_id)
    # 确认列存在
    col = await db.get(KanbanColumn, data.column_id)
    if not col or col.project_id != project_id:
        raise HTTPException(status_code=400, detail="列不存在")

    max_order = (await db.execute(
        select(func.coalesce(func.max(KanbanCard.sort_order), -1)).where(
            KanbanCard.column_id == data.column_id)
    )).scalar() or -1
    card = KanbanCard(
        column_id=data.column_id, title=data.title,
        description=data.description, priority=data.priority,
        due_date=data.due_date, assignee=data.assignee,
        sort_order=max_order + 1,
    )
    db.add(card)
    await db.commit()
    await db.refresh(card)
    return _card_out(card)


@router.put("/{project_id}/kanban/cards/{card_id}")
async def update_card(project_id: str, card_id: str, data: CardUpdateIn, db: AsyncSession = Depends(get_db)):
    card = await db.get(KanbanCard, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="卡片不存在")
    col = await db.get(KanbanColumn, card.column_id)
    if not col or col.project_id != project_id:
        raise HTTPException(status_code=404, detail="卡片不在该项目")

    update_data = data.model_dump(exclude_none=True)
    for k, v in update_data.items():
        setattr(card, k, v)
    await db.commit()
    await db.refresh(card)
    return _card_out(card)


@router.delete("/{project_id}/kanban/cards/{card_id}")
async def delete_card(project_id: str, card_id: str, db: AsyncSession = Depends(get_db)):
    card = await db.get(KanbanCard, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="卡片不存在")
    col = await db.get(KanbanColumn, card.column_id)
    if not col or col.project_id != project_id:
        raise HTTPException(status_code=404, detail="卡片不在该项目")
    await db.delete(card)
    await db.commit()
    return {"ok": True}


@router.put("/{project_id}/kanban/cards/{card_id}/move")
async def move_card(project_id: str, card_id: str, data: CardMoveIn, db: AsyncSession = Depends(get_db)):
    """移动卡片到指定列/位置。重新计算列内 sort_order。"""
    card = await db.get(KanbanCard, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="卡片不存在")

    # 确认目标列存在
    target_col = await db.get(KanbanColumn, data.column_id)
    if not target_col or target_col.project_id != project_id:
        raise HTTPException(status_code=400, detail="目标列不存在")

    old_col_id = card.column_id
    card.column_id = data.column_id
    await db.flush()

    # 重新排列目标列的 sort_order
    target_cards = (await db.execute(
        select(KanbanCard).where(KanbanCard.column_id == data.column_id).order_by(KanbanCard.sort_order)
    )).scalars().all()

    # 将要移动的卡片插入到指定位置
    ordered = [c for c in target_cards if c.id != card_id]
    insert_at = min(data.sort_order, len(ordered))
    ordered.insert(insert_at, card)
    for i, c in enumerate(ordered):
        c.sort_order = i

    # 重新排列原列的 sort_order（如果跨列）
    if old_col_id != data.column_id:
        old_cards = (await db.execute(
            select(KanbanCard).where(KanbanCard.column_id == old_col_id).order_by(KanbanCard.sort_order)
        )).scalars().all()
        for i, c in enumerate(old_cards):
            c.sort_order = i

    await db.commit()
    await db.refresh(card)
    return _card_out(card)


# ── 同步 PlanTask → 看板（可选） ──

@router.post("/{project_id}/kanban/sync-plan-tasks")
async def sync_plan_tasks(project_id: str, db: AsyncSession = Depends(get_db)):
    """将项目的 PlanTask 同步到看板的「待办」列（仅导入尚未关联的）。"""
    await _get_project(db, project_id)

    cols = (await db.execute(
        select(KanbanColumn).where(
            KanbanColumn.project_id == project_id, KanbanColumn.is_default == True
        ).order_by(KanbanColumn.sort_order)
    )).scalars().all()
    todo_col = next((c for c in cols if c.title == "待办"), cols[0] if cols else None)
    if not todo_col:
        raise HTTPException(status_code=400, detail="没有可用列，请先初始化看板")

    tasks = (await db.execute(
        select(PlanTask).where(
            PlanTask.status == "todo"
        ).order_by(PlanTask.day_index)
    )).scalars().all()

    existing_refs = {c.plan_task_id for c in (await db.execute(
        select(KanbanCard).where(
            KanbanCard.column_id.in_([c.id for c in cols]),
            KanbanCard.plan_task_id.isnot(None),
        )
    )).scalars()}

    imported = 0
    for task in tasks:
        if task.id in existing_refs:
            continue
        max_order = (await db.execute(
            select(func.coalesce(func.max(KanbanCard.sort_order), -1)).where(
                KanbanCard.column_id == todo_col.id)
        )).scalar() or -1
        card = KanbanCard(
            column_id=todo_col.id, title=task.title,
            description=task.description or "",
            plan_task_id=task.id, sort_order=max_order + 1,
        )
        db.add(card)
        imported += 1

    await db.commit()
    return {"imported": imported}
