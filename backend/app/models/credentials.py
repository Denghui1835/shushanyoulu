"""按「能力」存的用户自有服务商配置。

为什么要单开一张表，而不是往 `users` 加列：凭据的**形状随服务商变**——
edge 不需要凭据，volc 要 app_id + access_token，azure 要 key + region，
LLM 要 api_key + base_url + model。加列会变成
`text_key / text_base / tts_volc_app_id / tts_azure_region / ...` 的组合爆炸，
而且每接一个新服务商都要再来一次迁移。

所以：**敏感项整体加密成一个 JSON blob**（`secret_encrypted`），
**非敏感项**（volc 集群、azure region、音色）放明文 JSON（`options_json`）。
`(user_id, capability)` 唯一 = 每档至多一个激活配置；删掉该行即回退系统默认。

capability 取值：`text`（对话/摘要/出题/计划）、`vision`（看图）、`tts`（听读/播客）。
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class UserProviderConfig(Base):
    __tablename__ = "user_provider_configs"
    __table_args__ = (
        UniqueConstraint("user_id", "capability", name="uq_user_provider_capability"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    capability: Mapped[str] = mapped_column(String(16))          # text | vision | tts
    provider: Mapped[str] = mapped_column(String(32))            # deepseek|dashscope|moonshot|zhipu|openai|custom|edge|volc|azure
    base_url: Mapped[str | None] = mapped_column(String(256), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # fernet(JSON)：{api_key} / {app_id, access_token} / {key} —— 按 provider 不同
    secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 非敏感项 JSON：volc cluster、azure region、voice_a/voice_b 等
    options_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
