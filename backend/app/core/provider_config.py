"""把库里的「用户自有服务商配置」重新注册进内存适配器表。

**为什么必须有这个模块**：适配器注册表（`api_client._adapters`）是**纯内存**的，
只在「用户点保存」那一刻写入（`api/profile.py`）。进程一重启，表就空了，
而 `users` 表里的密文还在 —— 于是用户的请求会**静默回落**到服务器全局 Key，
用户花了钱却跑了服务器的额度，且完全看不出来。

所以启动时必须从库里读回来重注册一遍。这也是单进程假设：
多 worker 部署下每个 worker 都要各自跑一次 `reload_user_adapters()`，
本项目是 SQLite 单机单 worker，超出范围但记在这里。
"""
import json
import logging

from sqlalchemy import select

from app.core.api_scheduler import api_client
from app.core.crypto import decrypt_secret
from app.database import async_session
from app.models import UserProviderConfig

logger = logging.getLogger("yuanqi.provider_config")

# 能直接建适配器的能力档（tts 不走 api_client，单独在 podcast_tts 里解析）
_ADAPTER_CAPABILITIES = ("text", "vision")


async def reload_user_adapters() -> int:
    """遍历所有用户配置，重建内存适配器。返回成功注册的档数。

    解密失败 / 缺必填凭据的档**跳过并 warning 点名**，不抛异常 ——
    一个用户的坏配置不该拦住整个服务启动。
    """
    registered = 0
    async with async_session() as db:
        rows = (await db.execute(select(UserProviderConfig))).scalars().all()

    for row in rows:
        if row.capability not in _ADAPTER_CAPABILITIES:
            continue
        secret = decrypt_secret(row.secret_encrypted, owner=f"{row.user_id}/{row.capability}")
        api_key = (secret or {}).get("api_key", "").strip()
        if not api_key:
            logger.warning(
                "用户 %s 的「%s」档未注册：凭据缺失或无法解密，该档将回落系统默认。"
                "（若是加密密钥变过，请让用户到个人中心重新填写）",
                row.user_id, row.capability)
            continue
        try:
            api_client.configure_user_adapter(
                row.user_id, api_key,
                base_url=row.base_url or None,
                model_name=row.model or None,
                capability=row.capability,
                provider=row.provider or "deepseek",
            )
            registered += 1
        except Exception as e:
            logger.warning("用户 %s 的「%s」档注册失败：%s", row.user_id, row.capability, e)

    if registered:
        logger.info("已为 %d 档用户自有服务商配置重建适配器", registered)
    return registered


def load_options(row: UserProviderConfig) -> dict:
    """读非敏感项（cluster / region / 音色）。坏 JSON 一律当空，不让它炸。"""
    try:
        data = json.loads(row.options_json or "{}")
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        logger.warning("用户 %s 的「%s」档 options_json 不是合法 JSON，已忽略",
                       row.user_id, row.capability)
        return {}
