"""LLM 调度相关模型（响应缓存 / 配额 / 调用日志，供 api_scheduler 使用）."""
from datetime import date, datetime

from sqlalchemy import String, Text, DateTime, Integer, Boolean, Float, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class APICache(Base):
    __tablename__ = "api_cache"

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    response_content: Mapped[str] = mapped_column(Text, default="")
    model_used: Mapped[str] = mapped_column(String(64), default="")
    tokens_input: Mapped[int] = mapped_column(Integer, default=0)
    tokens_output: Mapped[int] = mapped_column(Integer, default=0)
    ttl_days: Mapped[int] = mapped_column(Integer, default=30)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class APIQuota(Base):
    __tablename__ = "api_quotas"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    daily_limit: Mapped[int] = mapped_column(Integer, default=1_000_000)
    used_today: Mapped[int] = mapped_column(Integer, default=0)
    total_used: Mapped[int] = mapped_column(Integer, default=0)
    reset_at: Mapped[date] = mapped_column(default=date.today)


class APICallLog(Base):
    __tablename__ = "api_call_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    task_type: Mapped[str] = mapped_column(String(32), default="")
    model_name: Mapped[str] = mapped_column(String(64), default="")
    tokens_input: Mapped[int] = mapped_column(Integer, default=0)
    tokens_output: Mapped[int] = mapped_column(Integer, default=0)
    cost_estimate: Mapped[float] = mapped_column(Float, default=0.0)
    from_cache: Mapped[bool] = mapped_column(Boolean, default=False)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[str] = mapped_column(Text, default="")
    content_summary: Mapped[str] = mapped_column(Text, default="")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
