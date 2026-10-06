"""学习项目模型：书架中的一本「书」，其下组织各章节文档."""
import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Project(Base):
    """一个学习项目（书）。章节 = 归属于该 project 的 Document。"""
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    title: Mapped[str] = mapped_column(String(128), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    icon: Mapped[str] = mapped_column(String(16), default="📚")
    is_public: Mapped[bool] = mapped_column(default=False, index=True)  # 作品社区：是否公开到广场
    blank_enabled: Mapped[bool] = mapped_column(default=False)  # 按书配置：是否开启「关键词挖空」背诵
    kanban_enabled: Mapped[bool] = mapped_column(default=False)  # 看板视图开关
    # 社区（番茄+GitHub 式）新增字段
    subject: Mapped[str] = mapped_column(String(64), default="")       # 旧学科名（兼容，优先用 category）
    category: Mapped[str] = mapped_column(String(64), default="")      # 一级：学科门类，如 理学/工学
    category_sub: Mapped[str] = mapped_column(String(64), default="")  # 二级：一级学科，如 数学/人工智能
    learn_count: Mapped[int] = mapped_column(Integer, default=0)       # 被学习次数
    star_count: Mapped[int] = mapped_column(Integer, default=0)        # 被收藏次数
    fork_count: Mapped[int] = mapped_column(Integer, default=0)        # 被 Fork 次数
    # 书山 Hub（课程即仓库）字段
    visibility: Mapped[str] = mapped_column(String(16), default="private", index=True)  # private | unlisted | public
    license: Mapped[str] = mapped_column(String(64), default="")       # 许可协议（SPDX 风格），空 = 未声明
    allow_fork: Mapped[bool] = mapped_column(default=False)            # 是否允许被 Fork
    forked_from_id: Mapped[str] = mapped_column(String(36), default="")  # 直接上游仓库
    upstream_id: Mapped[str] = mapped_column(String(36), default="")     # 根仓库（Fork 链顶端）
    is_shared: Mapped[bool] = mapped_column(default=False)             # 平台预置精品课（官方账号名下）
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
