"""学习项目模型：书架中的一本「书」，其下组织各章节文档."""
import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Project(Base):
    """一个学习项目（书）。章节 = 归属于该 project 的 Document。"""
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    title: Mapped[str] = mapped_column(String(128), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    icon: Mapped[str] = mapped_column(String(16), default="📚")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
