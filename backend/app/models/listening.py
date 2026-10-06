"""听读/收听模型 —— 把「生成、对齐、播放」的单位从一页升维成一讲。

为什么需要 Episode 这一层（而不是继续用 reading unit）：
- PDF 的阅读单元是**物理页**（`reading_content.py`），但没人想「听第 37 页」；
  人想听的是**一讲**——通勤路上放完一段，回来还在讲同一件事。
- 一期的音频要能被**全局复用**（平台预置精品课只合成一次，N 个人听同一份），
  所以生成结果必须落库、按内容寻址，而不是每次现算。

`span_start/span_end` 指向**本章内的阅读单元区间**（含两端），
所以不引入独立的章节表——`Project` 即书即仓库，`Document` 即章。
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    String, Text, DateTime, Integer, Float, Index, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Episode(Base):
    """一讲（一期）——听读的最小可播单位。

    同一章会被自动切成 1..N 讲（长章按字数预算切，见 core/episodes.py），
    所以 `(document_id, span_start, span_end)` 唯一确定一讲。
    """
    __tablename__ = "episodes"
    __table_args__ = (
        Index("ix_episode_doc_span", "document_id", "span_start", "span_end", "kind"),
        Index("ix_episode_project", "project_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    document_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)

    kind: Mapped[str] = mapped_column(String(16), default="read")   # read | narrate | dialogue
    # 本章内的阅读单元区间（含两端）；span_end=None 表示到章末
    span_start: Mapped[int] = mapped_column(Integer, default=0)
    span_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)            # 同章内的第几讲，从 0 起

    title: Mapped[str] = mapped_column(String(256), default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|running|done|error
    error: Mapped[str] = mapped_column(Text, default="")

    provider: Mapped[str] = mapped_column(String(32), default="")
    voice: Mapped[str] = mapped_column(String(64), default="")
    speed: Mapped[float] = mapped_column(Float, default=1.0)

    # 正文内容哈希（含音色/语速/引擎），换任一条件都会让旧音频失效
    source_hash: Mapped[str] = mapped_column(String(64), default="")
    # 音频文件的内容哈希 = listen_cache 里的文件名（见 core/listen_tts.cache_key）
    audio_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    audio_seconds: Mapped[float] = mapped_column(Float, default=0.0)

    timeline: Mapped[str] = mapped_column(Text, default="")   # 逐句时间轴 JSON

    # 生成进度：SSE 只读这两个数字，生成任务自己写（见 api/listen.py）
    progress_done: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now())


class PlaybackProgress(Base):
    """断点续听：某人在某一讲听到哪儿了。

    按 (user_id, episode_id) 唯一。未登录时 user_id 是 `local_user`
    （见 core/access.owner_id），所以本地单人使用照常工作。
    """
    __tablename__ = "playback_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "episode_id", name="uq_progress_user_episode"),
        Index("ix_progress_user_updated", "user_id", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    episode_id: Mapped[str] = mapped_column(String(36), index=True)
    document_id: Mapped[str] = mapped_column(String(36), index=True)
    position_ms: Mapped[int] = mapped_column(Integer, default=0)
    finished: Mapped[int] = mapped_column(Integer, default=0)   # 0/1，听完的讲不再出现在「继续收听」
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now())