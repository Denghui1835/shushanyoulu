"""用户自有 API Key 加密：cryptography.fernet 对称加密。

密钥来源，按优先级：
  1. config.API_KEY_ENCRYPT_SECRET（建议在 .env 固定设置）
  2. DATA_DIR/.api_key_secret —— 首次自动生成并落盘，之后复用

**为什么不能像以前那样「留空就每次随机」**：那样进程一重启就换密钥，
库里已存的密文全部解不开，用户必须重新填写；而且这件事没有任何提示。
现在默认配置也能跨重启解密。

另外，旧代码直接把环境变量的字符串当 Fernet key 用（`Fernet(secret.encode())`），
而 Fernet 只接受 urlsafe-base64 编码的 32 字节密钥 —— 用户随手填一句中文或
一个短口令就会**直接抛异常**。现在统一用 sha256 派生成合法密钥，填什么都能用。
"""
import base64
import hashlib
import json
import logging
from pathlib import Path

from cryptography.fernet import Fernet

from app.config import settings, DATA_DIR

logger = logging.getLogger("yuanqi.crypto")

_fernet = None

# 自动生成的密钥落盘位置（放在数据目录，随 data/ 一起被 gitignore）
_SECRET_FILE = Path(DATA_DIR) / ".api_key_secret"


def _derive_key(secret: str) -> bytes:
    """把任意字符串派生成合法的 Fernet 密钥（32 字节 urlsafe-base64）。"""
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())


def _load_or_create_file_key() -> bytes:
    """没有显式配置时，用数据目录里的密钥文件；没有就生成一次并落盘。"""
    try:
        if _SECRET_FILE.exists():
            raw = _SECRET_FILE.read_bytes().strip()
            if raw:
                return raw
        key = Fernet.generate_key()
        _SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SECRET_FILE.write_bytes(key)
        logger.warning(
            "未设置 API_KEY_ENCRYPT_SECRET，已自动生成密钥并保存到 %s。"
            "换机器/重装请一并带走该文件，否则已保存的 API Key 将无法解密。", _SECRET_FILE)
        return key
    except OSError as e:
        # 磁盘不可写等极端情况：退回进程级随机密钥（本次运行内可用，重启失效）
        logger.error("无法读写密钥文件 %s（%s），本次运行改用临时密钥，"
                     "重启后已保存的 Key 将无法解密", _SECRET_FILE, e)
        return Fernet.generate_key()


def _fernet_instance() -> Fernet:
    global _fernet
    if _fernet is None:
        secret = (settings.api_key_encrypt_secret or "").strip()
        key = _derive_key(secret) if secret else _load_or_create_file_key()
        _fernet = Fernet(key)
    return _fernet


# ---------------------------------------------------------------- 单值（旧的 LLM Key）

def encrypt_api_key(plain: str) -> str:
    return _fernet_instance().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_api_key(encrypted: str) -> str:
    try:
        return _fernet_instance().decrypt(encrypted.encode("utf-8")).decode("utf-8")
    except Exception:
        return ""


# ---------------------------------------------------------------- JSON blob（按能力的凭据）

def encrypt_secret(payload: dict) -> str:
    """把一组凭据（如 {api_key} / {app_id, access_token}）整体加密成一串密文。"""
    raw = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
    return _fernet_instance().encrypt(raw).decode("utf-8")


def decrypt_secret(encrypted: str | None, *, owner: str = "") -> dict:
    """解密凭据 blob。失败返回 {}（调用方据此把该档标成「需重新填写」）。

    失败是**可能真实发生**的：旧版本没有固定密钥，历史上存的密文解不开。
    这里不抛异常，但一定留日志，别让它静默。
    """
    if not encrypted:
        return {}
    try:
        raw = _fernet_instance().decrypt(encrypted.encode("utf-8")).decode("utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("解密凭据失败%s：%s（该配置需重新填写）",
                       f"（{owner}）" if owner else "", e)
        return {}
