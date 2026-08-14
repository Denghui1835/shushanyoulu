"""看板模型：KanbanColumn + KanbanCard，不修改现有任务表。

KanbanCard 可独立存在，也可通过 plan_task_id 关联学习计划任务。
"""
import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, Integer, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class KanbanColumn(Base):
    __tablename__ = "kanban_columns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    title: Mapped[str] = mapped_column(String(64), default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)  # Todo/InProgress/Done 为 True


class KanbanCard(Base):
    __tablename__ = "kanban_cards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    column_id: Mapped[str] = mapped_column(String(36), index=True)
    title: Mapped[str] = mapped_column(String(256), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(16), default="medium")  # high / medium / low
    due_date: Mapped[str | None] = mapped_column(String(16), nullable=True)  # YYYY-MM-DD
    assignee: Mapped[str] = mapped_column(String(64), default="")  # 负责人名
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    plan_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # 关联学习计划任务（可选）
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
