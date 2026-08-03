"""社区账号 API：注册 / 登录 / 登出 / 我的信息与项目。

第一个注册的账号成为「主人」，认领现有 local_user 数据（保留所有项目/聊天/计划）。
之后注册的是普通用户（自己的书架从零开始，可浏览广场、一键学习公开项目）。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.auth import get_current_user, hash_password, verify_password, issue_token, revoke_token, _extract_token
from app.core.wechat_auth import get_wechat_user_info
from app.models import User, Project

logger = logging.getLogger("yuanqi.api.auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterIn(BaseModel):
    username: str
    password: str


class LoginIn(BaseModel):
    username: str
    password: str


def _serialize_user(u: User) -> dict:
    return {"id": u.id, "username": u.username or "", "name": u.name}


@router.post("/register")
async def register(data: RegisterIn, db: AsyncSession = Depends(get_db)):
    username = (data.username or "").strip()
    password = data.password or ""
    if len(username) < 2:
        raise HTTPException(status_code=400, detail="用户名至少 2 个字符")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 位")

    taken = (await db.execute(select(User).where(User.username == username))).scalars().first()
    if taken:
        raise HTTPException(status_code=400, detail="用户名已被注册")

    # 首个注册账号 = 主人，认领 local_user 数据
    any_registered = (await db.execute(
        select(User).where(User.username.is_not(None), User.username != "").limit(1)
    )).scalars().first()
    if any_registered is None:
        u = await db.get(User, "local_user")
        if u is None:
            u = User(id="local_user", name=username)
            db.add(u)
            await db.flush()
        u.username = username
        u.password_hash = hash_password(password)
        logger.info("首个账号注册：认领 local_user 数据，用户名=%s", username)
    else:
        u = User(username=username, password_hash=hash_password(password), name=username)
        db.add(u)

    await db.commit()
    await db.refresh(u)
    token = await issue_token(db, u)
    return {"token": token, "user": _serialize_user(u)}


@router.post("/login")
async def login(data: LoginIn, db: AsyncSession = Depends(get_db)):
    u = (await db.execute(select(User).where(User.username == (data.username or "").strip()))).scalars().first()
    if not u or not verify_password(data.password or "", u.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = await issue_token(db, u)
    return {"token": token, "user": _serialize_user(u)}


@router.post("/logout")
async def logout(request: Request, db: AsyncSession = Depends(get_db)):
    token = _extract_token(request)
    if token:
        await revoke_token(db, token)
    return {"ok": True}


# ---------------------------------------------------------------- 微信登录 / 绑定

class WechatLoginIn(BaseModel):
    code: str


@router.post("/wechat/login")
async def wechat_login(data: WechatLoginIn, db: AsyncSession = Depends(get_db)):
    """微信登录：code → openid → 已有账号则登录，否则自动创建。"""
    try:
        info = await get_wechat_user_info(data.code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    openid = info["openid"]
    u = (await db.execute(select(User).where(User.wechat_openid == openid))).scalars().first()
    is_new = u is None
    if u is None:
        u = User(wechat_openid=openid, name="微信用户", username=None)
        db.add(u)
        await db.commit()
        await db.refresh(u)
    token = await issue_token(db, u)
    return {"token": token, "user": _serialize_user(u), "is_new": is_new}


@router.post("/wechat/bind")
async def wechat_bind(data: WechatLoginIn, user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    """已登录用户绑定微信。"""
    try:
        info = await get_wechat_user_info(data.code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    openid = info["openid"]
    other = (await db.execute(select(User).where(User.wechat_openid == openid))).scalars().first()
    if other and other.id != user.id:
        raise HTTPException(status_code=400, detail="该微信已绑定其他账号")
    user.wechat_openid = openid
    await db.commit()
    return {"ok": True, "wechat_bound": True}


@router.post("/wechat/unbind")
async def wechat_unbind(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    user.wechat_openid = None
    await db.commit()
    return {"ok": True, "wechat_bound": False}


@router.get("/me")
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """当前用户信息 + 我拥有的项目（含发布状态），供社区页展示。"""
    projects = (await db.execute(
        select(Project).where(Project.user_id == user.id).order_by(Project.created_at)
    )).scalars().all()
    return {
        "user": _serialize_user(user),
        "projects": [{
            "id": p.id, "title": p.title, "description": p.description,
            "icon": p.icon, "is_public": bool(p.is_public),
        } for p in projects],
    }
