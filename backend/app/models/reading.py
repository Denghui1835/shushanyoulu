"""阅读功能模型：批注(Annotation)、总结(DocSummary)、AI 播客文稿(PodcastScript)."""
import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Annotation(Base):
    """一条文本批注。定位方式：阅读单元(unit_index) + 单元内字符偏移。

    unit_type: 'page'(PDF 实际页) 或 'chunk'(非 PDF 分块)
    start_offset/end_offset: 该单元文本内的 [start, end) 字符区间。

    时间戳用 Python 侧 default/onupdate，避免 async 下 server_default
    造成的属性过期后同步懒加载（MissingGreenlet）。
    """
    __tablename__ = "annotations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"), index=True)
    unit_type: Mapped[str] = mapped_column(String(16), default="chunk")  # page / chunk
    unit_index: Mapped[int] = mapped_column(Integer, default=0)
    start_offset: Mapped[int] = mapped_column(Integer, default=0)
    end_offset: Mapped[int] = mapped_column(Integer, default=0)
    selected_text: Mapped[str] = mapped_column(Text, default="")  # 冗余：被批注的原文片段
    content: Mapped[str] = mapped_column(Text, default="")         # 批注内容
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class DocSummary(Base):
    """一条总结。scope='overall' 整体 / 'page' 页级 / 'story' 听书式章节总结 / 'concept' 概念要点。

    unit_index 仅在 scope='page' 时使用，对应阅读单元序号；其余 scope 为章节级（unit_index 为空）。
    status: generating / done / error
    """
    __tablename__ = "doc_summaries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"), index=True)
    scope: Mapped[str] = mapped_column(String(16), default="overall")  # overall / page / story / concept
    unit_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="generating")  # generating / done / error
    error: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class PodcastScript(Base):
    """一期「AI 播客」文稿：基于单个阅读单元（章节/页）生成的双人主播对谈。

    unit_index 对应阅读单元序号（见 reading_content.get_reading_units）。
    content 为双人对谈文稿（每行「主播A：…/主播B：…」），audio_path 指向合成后的 mp3。
    status: generating / done / error；生成文稿时会先删旧记录重建（幂等），旧音频一并清理。
    """
    __tablename__ = "podcast_scripts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"), index=True)
    unit_index: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text, default="")
    audio_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="generating")  # generating / done / error
    error: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
