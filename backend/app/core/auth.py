"""社区认证：密码哈希（PBKDF2，标准库）、token 签发/校验、get_current_user 依赖。

设计：只社区相关接口需要登录（伴学/书架等本地功能保持免登录）。
第一个注册的账号成为「主人」，认领现有 local_user 数据；之后注册的是普通用户。
"""
import hashlib
import secrets

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User, AuthToken

_PBKDF2_ITER = 100_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 salt.encode("utf-8"), _PBKDF2_ITER).hex()
    return f"pbkdf2${_PBKDF2_ITER}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, it, salt, digest = stored.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                   salt.encode("utf-8"), int(it)).hex()
        return secrets.compare_digest(calc, digest)
    except (ValueError, TypeError):
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def _extract_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return None


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """从 Authorization: Bearer <token> 解析当前用户；无效返回 401。"""
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="请先登录（社区功能需要账号）")
    row = (await db.execute(select(AuthToken).where(AuthToken.token == token))).scalars().first()
    if not row:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    user = await db.get(User, row.user_id)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


async def issue_token(db: AsyncSession, user: User) -> str:
    token = new_token()
    db.add(AuthToken(user_id=user.id, token=token))
    await db.commit()
    return token


async def revoke_token(db: AsyncSession, token: str) -> None:
    await db.execute(delete(AuthToken).where(AuthToken.token == token))
    await db.commit()
