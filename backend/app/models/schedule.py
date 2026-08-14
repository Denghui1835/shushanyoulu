"""手动计划表：Schedule（周计划） + ScheduleSlot（每日时间格）。

与 AI 生成的 LearningPlan/PlanTask 互补——这里让用户自己安排每天的时间段做什么。
"""
import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, Integer, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Schedule(Base):
    """一个周/天计划表（按 project 分组）。"""
    __tablename__ = "schedules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    title: Mapped[str] = mapped_column(String(128), default="本周计划")
    week_start_date: Mapped[str] = mapped_column(String(16), index=True)  # YYYY-MM-DD（周一日期）
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ScheduleSlot(Base):
    """某个时间段的任务安排。day_of_week: 0=周一…6=周日。"""
    __tablename__ = "schedule_slots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    schedule_id: Mapped[str] = mapped_column(String(36), index=True)
    day_of_week: Mapped[int] = mapped_column(Integer, default=0)    # 0-6
    start_time: Mapped[str] = mapped_column(String(8), default="08:00")   # HH:MM
    end_time: Mapped[str] = mapped_column(String(8), default="09:00")     # HH:MM
    title: Mapped[str] = mapped_column(String(256), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    color: Mapped[str] = mapped_column(String(16), default="#e6f4ff")  # 背景色
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    notify_on_start: Mapped[bool] = mapped_column(Boolean, default=False)  # 该时间段开始时浏览器通知
    completed: Mapped[bool] = mapped_column(Boolean, default=False)  # 该时间段任务已完成


class PlanNotification(Base):
    """防重复通知记录：已发送的通知写入此表，发送前检查避免重复推送。"""
    __tablename__ = "plan_notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    schedule_id: Mapped[str] = mapped_column(String(36), index=True)
    slot_id: Mapped[str] = mapped_column(String(36), index=True)
    notify_date: Mapped[str] = mapped_column(String(16), index=True)  # YYYY-MM-DD
    notified_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
