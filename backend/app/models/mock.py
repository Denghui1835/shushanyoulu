"""全真模拟考试成绩记录模型."""
import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, Float, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class MockRecord(Base):
    """一次全真模拟考试的成绩记录（科目 + 总分 + 各部分得分 + 合格与否）。"""

    __tablename__ = "mock_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    subject: Mapped[str] = mapped_column(String(16), default="python")   # python / c
    total: Mapped[float] = mapped_column(Float, default=0.0)
    max_score: Mapped[float] = mapped_column(Float, default=100.0)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    section_scores: Mapped[str] = mapped_column(Text, default="[]")      # JSON: [{name,score,max_score}]
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
