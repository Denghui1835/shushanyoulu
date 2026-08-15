"""「一起学」社交模型 — 学习动态 + 点赞鼓励.

学习行为（打卡/任务/课程/模拟）自动生成动态，成员可互相点赞鼓励并积累元气值。
"""
import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class SocialPost(Base):
    """一条学习动态（系统根据学习行为自动发布）。"""

    __tablename__ = "social_posts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    username: Mapped[str] = mapped_column(String(64), default="学习者")  # 冗余显示名
    kind: Mapped[str] = mapped_column(String(16), default="activity")   # checkin/task/lesson/mock/plan
    content: Mapped[str] = mapped_column(Text, default="")
    points: Mapped[int] = mapped_column(Integer, default=0)             # 该行为攒的元气值
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class SocialLike(Base):
    """给某条学习动态点赞鼓励（每人每条一次）。"""

    __tablename__ = "social_likes"
    __table_args__ = (UniqueConstraint("post_id", "user_id", name="uq_like_post_user"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    post_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
