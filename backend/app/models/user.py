"""User profile — the "learner" that the companion accompanies."""
import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(64), default="学习者")
    goal: Mapped[str] = mapped_column(Text, default="")          # 学习目标（如"考取教资"）
    goal_detail: Mapped[str] = mapped_column(Text, default="")   # 目标详情/考试时间等
    daily_minutes: Mapped[int] = mapped_column(Integer, default=30)  # 每天可投入时间(分钟)
    active_plan_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # 当前生效的学习计划
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    @property
    def is_onboarded(self) -> bool:
        """Whether the companion has gathered enough info to build a plan."""
        return bool(self.goal.strip())
