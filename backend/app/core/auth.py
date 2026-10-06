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
    if not user.is_active:
        raise HTTPException(status_code=403, detail="该账号已被停用")
    return user


async def get_optional_user(request: Request, db: AsyncSession = Depends(get_db)) -> User | None:
    """可选认证：有合法 token 返回该用户，否则返回 None（本地免登录场景也用）。

    已停用的账号**必须抛 403，不能返回 None**：`core/access.py::owner_id(None)` 在
    `allow_anonymous_local=True` 时会回退到 `local_user`（即主人），把被封的人当匿名
    放行反而拿到了主人的全部数据——封禁就成了摆设。所以这里宁可报错也不能降级。
    """
    token = _extract_token(request)
    if not token:
        return None
    row = (await db.execute(select(AuthToken).where(AuthToken.token == token))).scalars().first()
    if not row:
        return None
    user = await db.get(User, row.user_id)
    if user is not None and not user.is_active:
        raise HTTPException(status_code=403, detail="该账号已被停用")
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """管理后台专用依赖：非管理员一律 403（get_current_user 已挡掉未登录与已停用）。"""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


async def issue_token(db: AsyncSession, user: User) -> str:
    token = new_token()
    db.add(AuthToken(user_id=user.id, token=token))
    await db.commit()
    return token


async def revoke_token(db: AsyncSession, token: str) -> None:
    await db.execute(delete(AuthToken).where(AuthToken.token == token))
    await db.commit()


async def revoke_all_tokens(db: AsyncSession, user_id: str, keep: str | None = None) -> int:
    """吊销某用户的全部登录令牌 —— 强制下线的唯一手段。

    这里没有「每次请求校验密码」的机制，token 一旦签发就长期有效，所以
    重置密码/停用账号若不删 token，等于什么都没做。

    `keep`：保留某一枚 token 不删（管理员改自己密码时别把自己踢下线）。
    返回实际删掉的行数。**不 commit**，由调用方与其它写操作一起提交。
    """
    stmt = delete(AuthToken).where(AuthToken.user_id == user_id)
    if keep:
        stmt = stmt.where(AuthToken.token != keep)
    result = await db.execute(stmt)
    return int(result.rowcount or 0)
