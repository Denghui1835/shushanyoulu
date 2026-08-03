"""用户自有 API Key 加密：cryptography.fernet 对称加密。

密钥来源 config.API_KEY_ENCRYPT_SECRET（建议在 .env 固定设置，否则每次启动随机生成，
重启后旧 Key 无法解密、用户需重新填写）。
"""
from cryptography.fernet import Fernet

from app.config import settings

_fernet = None


def _fernet_instance() -> Fernet:
    global _fernet
    if _fernet is None:
        secret = (settings.api_key_encrypt_secret or "").strip()
        key = secret.encode() if secret else Fernet.generate_key()
        _fernet = Fernet(key)
    return _fernet


def encrypt_api_key(plain: str) -> str:
    return _fernet_instance().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_api_key(encrypted: str) -> str:
    try:
        return _fernet_instance().decrypt(encrypted.encode("utf-8")).decode("utf-8")
    except Exception:
        return ""
