"""个人中心 API：资料 + 统计 + 用户自有 API Key 管理。

用户填写自己的 LLM API Key 后，服务端加密存储并注册 per-user 适配器，
后续所有 AI 调用优先用用户 Key（见 main.py 的中间件 + api_scheduler.configure_user_adapter）。
"""
import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.auth import get_current_user
from app.core.crypto import encrypt_api_key, decrypt_api_key
from app.core.api_scheduler import api_client
from app.core.api_scheduler.adapters.base import AdapterConfig
from app.models import (
    User, Project, Document, Question, Flashcard, PodcastScript, StudyLog, CheckIn,
)

logger = logging.getLogger("yuanqi.api.profile")
router = APIRouter(prefix="/api/profile", tags=["profile"])


def _mask(key: str) -> str:
    if len(key) <= 8:
        return "****"
    return f"{key[:3]}****{key[-4:]}"


# ---------------------------------------------------------------- 资料 + 统计

@router.get("")
async def get_profile(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """当前用户完整信息 + 统计数据。"""
    project_ids = (await db.execute(
        select(Project.id).where(Project.user_id == user.id)
    )).scalars().all()
    doc_ids = (await db.execute(
        select(Document.id).where(Document.project_id.in_(project_ids))
    )).scalars().all() if project_ids else []

    counts = {"projects": len(project_ids)}
    if doc_ids:
        counts["questions"] = int((await db.execute(
            select(func.count()).select_from(Question).where(Question.document_id.in_(doc_ids)))).scalar() or 0)
        counts["flashcards"] = int((await db.execute(
            select(func.count()).select_from(Flashcard).where(Flashcard.document_id.in_(doc_ids)))).scalar() or 0)
        counts["podcasts"] = int((await db.execute(
            select(func.count()).select_from(PodcastScript).where(PodcastScript.document_id.in_(doc_ids)))).scalar() or 0)
    else:
        counts.update(questions=0, flashcards=0, podcasts=0)

    # 打卡 streak + 元气值
    checkin_dates = set((await db.execute(
        select(CheckIn.checkin_date).where(CheckIn.user_id == user.id)
    )).scalars().all())
    streak = 0
    d = date.today()
    if d.strftime("%Y-%m-%d") not in checkin_dates:
        d -= timedelta(days=1)
    while d.strftime("%Y-%m-%d") in checkin_dates:
        streak += 1
        d -= timedelta(days=1)
    points = int((await db.execute(
        select(func.coalesce(func.sum(StudyLog.points), 0)).where(StudyLog.user_id == user.id)
    )).scalar() or 0)

    return {
        "user": {
            "id": user.id, "username": user.username or "", "name": user.name,
            "goal": user.goal, "goal_detail": user.goal_detail,
            "daily_minutes": user.daily_minutes,
            "wechat_bound": bool(user.wechat_openid),
            "login_method": "wechat" if user.wechat_openid and not user.username else "password",
            "api_key_set": bool(user.api_key_encrypted),
        },
        "stats": {**counts, "streak": streak, "points": points, "checkin_days": len(checkin_dates)},
    }


class ProfileUpdate(BaseModel):
    name: str | None = None
    goal: str | None = None
    goal_detail: str | None = None
    daily_minutes: int | None = None


@router.patch("")
async def update_profile(data: ProfileUpdate, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    if data.name is not None:
        user.name = data.name.strip() or user.name
    if data.goal is not None:
        user.goal = data.goal.strip()
    if data.goal_detail is not None:
        user.goal_detail = data.goal_detail.strip()
    if data.daily_minutes is not None:
        user.daily_minutes = max(1, min(600, data.daily_minutes))
    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- 用户自有 API Key

@router.get("/apikey")
async def get_apikey(user: User = Depends(get_current_user)):
    """返回 API 配置（Key 打码）。"""
    if not user.api_key_encrypted:
        return {"configured": False, "masked_key": "", "base_url": "", "model": ""}
    return {
        "configured": True,
        "masked_key": _mask(decrypt_api_key(user.api_key_encrypted)),
        "base_url": user.api_base_url or "",
        "model": user.api_model or "",
    }


class ApiKeyIn(BaseModel):
    api_key: str
    base_url: str = ""
    model: str = ""


@router.put("/apikey")
async def save_apikey(data: ApiKeyIn, user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    """保存用户自有 API Key（明文传入，加密存储，不记日志）。"""
    api_key = (data.api_key or "").strip()
    if len(api_key) < 8:
        raise HTTPException(status_code=400, detail="API Key 格式不正确")
    base_url = (data.base_url or "").strip()
    model = (data.model or "").strip() or "deepseek-chat"
    # 先测试连通性，失败则不入库
    try:
        api_client.configure_user_adapter(f"t{user.id}", api_key, base_url or None, model)
        adapter = api_client.get_adapter("deepseek-chat", user_id=f"t{user.id}")
        resp = await adapter.chat_completion(
            [{"role": "user", "content": "你好，请只回复：OK"}],
            AdapterConfig(
                temperature=0.1, max_tokens=10, timeout=20),
        )
        if not (resp.content or "").strip():
            raise RuntimeError("返回为空")
    except Exception as e:
        api_client.remove_user_adapter(f"t{user.id}")
        raise HTTPException(status_code=400, detail=f"Key 测试失败：{str(e)[:120]}")

    # 正式注册 + 入库
    user.api_key_encrypted = encrypt_api_key(api_key)
    user.api_base_url = base_url or None
    user.api_model = model
    api_client.configure_user_adapter(user.id, api_key, base_url or None, model)
    await db.commit()
    logger.info("用户 %s 配置了自有 API Key", user.id)
    return {"ok": True, "configured": True, "masked_key": _mask(api_key)}


@router.delete("/apikey")
async def delete_apikey(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """删除用户自定义 Key，回退系统默认。"""
    user.api_key_encrypted = None
    user.api_base_url = None
    user.api_model = None
    api_client.remove_user_adapter(user.id)
    await db.commit()
    return {"ok": True, "configured": False}


@router.post("/apikey/test")
async def test_apikey(data: ApiKeyIn, user: User = Depends(get_current_user)):
    """用给定的 Key 发一条极短请求验证可用性。"""
    api_key = (data.api_key or "").strip()
    if len(api_key) < 8:
        raise HTTPException(status_code=400, detail="API Key 格式不正确")
    try:
        api_client.configure_user_adapter(f"t{user.id}", api_key, (data.base_url or "").strip() or None,
                                          (data.model or "").strip() or "deepseek-chat")
        adapter = api_client.get_adapter("deepseek-chat", user_id=f"t{user.id}")
        resp = await adapter.chat_completion(
            [{"role": "user", "content": "你好，请只回复：OK"}],
            AdapterConfig(
                temperature=0.1, max_tokens=10, timeout=20),
        )
        api_client.remove_user_adapter(f"t{user.id}")
        if not (resp.content or "").strip():
            raise RuntimeError("返回为空")
        return {"ok": True, "message": "连接成功"}
    except HTTPException:
        raise
    except Exception as e:
        api_client.remove_user_adapter(f"t{user.id}")
        raise HTTPException(status_code=400, detail=f"连接失败：{str(e)[:120]}")
