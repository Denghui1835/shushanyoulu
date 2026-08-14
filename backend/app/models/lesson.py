"""深度教学模式模型 — 讲→考→判→评 的苏格拉底式一对一教学会话."""
import json
import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class TopicProgress(Base):
    """深度教学考点学习进度：标记 已掌握 / 待复习，跨会话可查。"""

    __tablename__ = "topic_progress"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    subject: Mapped[str] = mapped_column(String(64), default="")
    topic: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(16), default="learning")  # learning / mastered / review
    times: Mapped[int] = mapped_column(Integer, default=0)               # 学习次数
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Lesson(Base):
    """一次深度教学会话。step 流转：teach → question → evaluate → (下一张卡) → ... → done"""

    __tablename__ = "lessons"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    subject: Mapped[str] = mapped_column(String(64), default="")      # 学科，如 3DGS / 数学建模
    topic: Mapped[str] = mapped_column(String(128), default="")       # 知识点，如 三步框架
    step: Mapped[str] = mapped_column(String(16), default="teach")    # teach / question / evaluate / done
    card: Mapped[str] = mapped_column(Text, default="{}")             # 当前卡 JSON
    history: Mapped[str] = mapped_column(Text, default="[]")          # 问答历史 JSON list
    rounds: Mapped[int] = mapped_column(Integer, default=0)           # 已完成的问答轮次
    status: Mapped[str] = mapped_column(String(16), default="active") # active / done
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # ---- helpers ----
    def get_card(self) -> dict:
        try:
            return json.loads(self.card or "{}")
        except json.JSONDecodeError:
            return {}

    def set_card(self, card: dict) -> None:
        self.card = json.dumps(card, ensure_ascii=False)

    def get_history(self) -> list:
        try:
            return json.loads(self.history or "[]")
        except json.JSONDecodeError:
            return []

    def append_history(self, item: dict) -> None:
        h = self.get_history()
        h.append(item)
        self.history = json.dumps(h, ensure_ascii=False)
