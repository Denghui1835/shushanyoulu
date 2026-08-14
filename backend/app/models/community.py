"""社区协作模型 — 番茄小说生态 + GitHub 协作机制.

- ProjectStar：收藏（star），类似 GitHub star / 番茄收藏
- ProjectFork：Fork 关系（谁的课程复制成了谁的新课程）
- ProjectSuggestion：修改建议（类似 GitHub issue/PR：学习者对课程提改进建议，作者可采纳）
"""
import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, Integer, Boolean, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class ProjectStar(Base):
    """用户收藏了一个公开课程。"""
    __tablename__ = "project_stars"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_star_project_user"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ProjectFork(Base):
    """一次 Fork：from_project 被某用户复制成了 new_project。"""
    __tablename__ = "project_forks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    from_project_id: Mapped[str] = mapped_column(String(36), index=True)
    new_project_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ProjectSuggestion(Base):
    """对某公开课程的一条修改建议（GitHub issue 风格）。"""
    __tablename__ = "project_suggestions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)      # 提建议的人
    username: Mapped[str] = mapped_column(String(64), default="匿名")  # 冗余存名字，方便显示
    content: Mapped[str] = mapped_column(Text, default="")            # 建议内容
    status: Mapped[str] = mapped_column(String(16), default="open")   # open / accepted / rejected / applied
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
