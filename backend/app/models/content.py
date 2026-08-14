"""Learning content models — documents, chunks, knowledge tree, questions, flashcards."""
import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, Integer, Float, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Document(Base):
    """一份文档；在书架结构下它即项目内的一个「章节」。

    project_id / chapter_title / sort_order 用于章节归属与排序。
    注：project_id 不加外键约束（与 PlanTask.document_id 一致），删除项目时显式批量清理，
    避免 SQLite FK 在级联删除时带来的顺序问题。
    """
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    title: Mapped[str] = mapped_column(String(256), default="")
    filename: Mapped[str] = mapped_column(String(256), default="")
    file_path: Mapped[str] = mapped_column(Text, default="")
    content_type: Mapped[str] = mapped_column(String(16), default="pdf")  # pdf / docx / md / txt / group
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    project_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    chapter_title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # 目录层级：content_type='group' 的节点是「部分/卷」分组（无文件），
    # 章节的 parent_id 指向所属分组；不设外键约束（沿用项目约定）。
    parent_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    # 整书引用与物理页范围（0 基，含）：整书导入/划页建章/调节器重切用。
    # 相邻章节范围可重叠，即边界页可同时归属两章；无外键约束（沿用现有约定）。
    book_file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Chunk(Base):
    """A chunk of document text used for generation and retrieval."""
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text, default="")
    heading: Mapped[str] = mapped_column(String(256), default="")  # 所在章节标题


class KnowledgePoint(Base):
    """A node in the knowledge tree."""
    __tablename__ = "knowledge_points"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"), index=True)
    parent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    title: Mapped[str] = mapped_column(String(256), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    order_index: Mapped[int] = mapped_column(Integer, default=0)


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"), index=True)
    chunk_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    qtype: Mapped[str] = mapped_column(String(16), default="choice")  # choice / fill / essay
    question: Mapped[str] = mapped_column(Text, default="")
    options: Mapped[str] = mapped_column(Text, default="[]")   # JSON list for choice
    answer: Mapped[str] = mapped_column(Text, default="")
    explanation: Mapped[str] = mapped_column(Text, default="")
    source_text: Mapped[str] = mapped_column(Text, default="")  # 溯源
    subtype: Mapped[str] = mapped_column(String(16), default="")  # 操作题子型：basic/applied/comprehensive（模拟考试用）
    # 题目管理：discarded=已弃用（软删除，列表默认隐藏，可恢复）；in_mistake_book=已加入错题本
    discarded: Mapped[bool] = mapped_column(default=False, index=True)
    in_mistake_book: Mapped[bool] = mapped_column(default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class QuizRecord(Base):
    """One attempt at answering a question."""
    __tablename__ = "quiz_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    question_id: Mapped[str] = mapped_column(String(36), ForeignKey("questions.id"), index=True)
    user_answer: Mapped[str] = mapped_column(Text, default="")
    correct: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Flashcard(Base):
    __tablename__ = "flashcards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"), index=True)
    front: Mapped[str] = mapped_column(Text, default="")
    back: Mapped[str] = mapped_column(Text, default="")
    visual: Mapped[str] = mapped_column(Text, default="")  # 图形化记忆提示：emoji + 联想画面
    status: Mapped[str] = mapped_column(String(16), default="new")  # new / learning / review
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    stability: Mapped[float] = mapped_column(Float, default=0.0)
    difficulty: Mapped[float] = mapped_column(Float, default=0.0)
    reps: Mapped[int] = mapped_column(Integer, default=0)
    lapses: Mapped[int] = mapped_column(Integer, default=0)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    discarded: Mapped[bool] = mapped_column(default=False, index=True)  # 已弃用（软删除，可恢复）
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
