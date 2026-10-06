"""个人中心 API：资料 + 统计 + 用户自有服务商配置（按能力分档）。

**为什么要按能力分档**：以前这里只有一个「API Key / Base URL / 模型名」三元组，
隐含假设「一个服务商包办所有 AI 能力」。但 DeepSeek 只有文本模型、没有语音；
用户想用语音，却连个能填豆包凭据的地方都没有，系统也无从知道该用哪个模型。

现在分三档：`text`（对话/摘要/出题）、`vision`（看图）、`tts`（听读/播客），
每档独立配、独立测、独立删，互不影响。见 `app/models/credentials.py`。
"""
import base64
import json
import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.auth import get_current_user
from app.core.crypto import encrypt_secret, decrypt_secret
from app.core.api_scheduler import api_client
from app.core.api_scheduler.adapters.base import AdapterConfig
from app.core.provider_presets import (
    CAPABILITIES, CREDENTIAL_FREE_PROVIDERS, find_preset, presets_for,
)
from app.core.provider_config import load_options
from app.models import (
    User, Project, Document, Question, Flashcard, PodcastScript, StudyLog, CheckIn,
    UserProviderConfig,
)

logger = logging.getLogger("yuanqi.api.profile")
router = APIRouter(prefix="/api/profile", tags=["profile"])

# 连接测试用的 1x1 透明 PNG。**必须发真图**：只发文字的话，一个纯文本模型
# 也能正常回话，测出来是「通」的 —— 但那恰恰证明不了它能看图。
_TEST_PNG_B64 = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNk"
                 "YAAAAAYAAjCB0C8AAAAASUVORK5CYII=")


def _mask(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "****"
    return f"{key[:3]}****{key[-4:]}"


def _check_capability(capability: str) -> str:
    if capability not in CAPABILITIES:
        raise HTTPException(status_code=404, detail=f"未知的能力档：{capability}")
    return capability


async def _get_row(db: AsyncSession, user_id: str, capability: str) -> UserProviderConfig | None:
    return (await db.execute(
        select(UserProviderConfig).where(
            UserProviderConfig.user_id == user_id,
            UserProviderConfig.capability == capability,
        )
    )).scalars().first()


def _secret_keys(capability: str, provider: str) -> list[dict]:
    preset = find_preset(capability, provider)
    return (preset or {}).get("secret_fields", [])


def _describe(row: UserProviderConfig | None, capability: str) -> dict:
    """把一个配置行描述给前端。**永不返回明文**。"""
    if row is None:
        return {
            "configured": False, "provider": "", "masked_key": "", "base_url": "",
            "model": "", "options": {}, "secret_set": {}, "secret_readable": True,
            "needs_refill": False,
        }
    secret = decrypt_secret(row.secret_encrypted, owner=f"{row.user_id}/{capability}") \
        if row.secret_encrypted else {}
    fields = _secret_keys(capability, row.provider)
    # 有密文但解不开（换过加密密钥）→ 明确告诉用户「要重填」，别假装配好了
    unreadable = bool(row.secret_encrypted) and not secret
    primary = ""
    for f in fields:
        if secret.get(f["key"]):
            primary = secret[f["key"]]
            break
    return {
        "configured": True,
        "provider": row.provider or "",
        "masked_key": _mask(primary),
        "base_url": row.base_url or "",
        "model": row.model or "",
        "options": load_options(row),
        "secret_set": {f["key"]: bool(secret.get(f["key"])) for f in fields},
        "secret_readable": not unreadable,
        "needs_refill": unreadable,
    }


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

    rows = (await db.execute(
        select(UserProviderConfig).where(UserProviderConfig.user_id == user.id)
    )).scalars().all()
    configured = {r.capability: True for r in rows}

    return {
        "user": {
            "id": user.id, "username": user.username or "", "name": user.name,
            "goal": user.goal, "goal_detail": user.goal_detail,
            "daily_minutes": user.daily_minutes,
            "wechat_bound": bool(user.wechat_openid),
            "login_method": "wechat" if user.wechat_openid and not user.username else "password",
            # 旧字段保留：mobile/ 的「自有 Key」标签还在读它
            "api_key_set": bool(user.api_key_encrypted) or configured.get("text", False),
            "providers_configured": {c: configured.get(c, False) for c in CAPABILITIES},
            "is_admin": bool(user.is_admin),
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


# ---------------------------------------------------------------- 服务商配置（按能力）

@router.get("/provider-presets")
async def get_provider_presets():
    """下发服务商预设表（前端照着渲染表单，不在前端硬编码）。"""
    return {
        "capabilities": {c: presets_for(c) for c in CAPABILITIES},
        "labels": {"text": "文本（对话 / 摘要 / 出题 / 计划）",
                   "vision": "视觉（看图 / 识别图表）",
                   "tts": "语音（听读 / 播客）"},
    }


@router.get("/providers")
async def get_providers(user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    """三档配置的当前状态（凭据一律打码/只报是否已填）。"""
    out = {}
    for cap in CAPABILITIES:
        out[cap] = _describe(await _get_row(db, user.id, cap), cap)
    return out


class ProviderConfigIn(BaseModel):
    provider: str
    base_url: str = ""
    model: str = ""
    # 只传要更新的凭据字段；**留空或省略 = 保留原值**（用户不想每次重敲 Key）
    secret: dict[str, str] = {}
    options: dict[str, str] = {}


def _merge_secret(existing: dict, incoming: dict) -> dict:
    merged = dict(existing or {})
    for k, v in (incoming or {}).items():
        if v is None:
            continue
        v = str(v).strip()
        if v:                      # 空串 = 不改这一项
            merged[k] = v
    return merged


def _require_fields(capability: str, provider: str, secret: dict) -> None:
    missing = [f["label"] for f in _secret_keys(capability, provider)
               if f.get("required") and not secret.get(f["key"])]
    if missing:
        raise HTTPException(status_code=400, detail=f"请填写：{'、'.join(missing)}")


@router.put("/providers/{capability}")
async def save_provider(capability: str, data: ProviderConfigIn,
                        user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    """保存某档配置。**先测通再入库**，测不通不留半成品。"""
    _check_capability(capability)
    provider = (data.provider or "").strip()
    if not find_preset(capability, provider):
        raise HTTPException(status_code=400, detail=f"「{capability}」档不支持服务商「{provider}」")

    row = await _get_row(db, user.id, capability)
    existing = decrypt_secret(row.secret_encrypted, owner=f"{user.id}/{capability}") \
        if row and row.secret_encrypted else {}
    secret = _merge_secret(existing, data.secret)
    _require_fields(capability, provider, secret)

    if provider not in CREDENTIAL_FREE_PROVIDERS:
        await _run_test(capability, provider, (data.base_url or "").strip(),
                        (data.model or "").strip(), secret, data.options, user.id)

    if row is None:
        row = UserProviderConfig(user_id=user.id, capability=capability)
        db.add(row)
    row.provider = provider
    row.base_url = (data.base_url or "").strip() or None
    row.model = (data.model or "").strip() or None
    row.secret_encrypted = encrypt_secret(secret) if secret else None
    row.options_json = json.dumps(data.options or {}, ensure_ascii=False)
    await db.commit()

    # 立刻生效：文本/视觉档重建内存适配器；语音档每次请求现查库，无需注册
    if capability in ("text", "vision"):
        api_client.configure_user_adapter(
            user.id, secret.get("api_key", ""),
            base_url=row.base_url, model_name=row.model,
            capability=capability, provider=provider)
    logger.info("用户 %s 配置了「%s」档服务商 %s", user.id, capability, provider)
    return {"ok": True, **_describe(row, capability)}


@router.delete("/providers/{capability}")
async def delete_provider(capability: str, user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    """删除某档配置，回退系统默认（文本→服务器 Key；语音→edge 免费档）。"""
    _check_capability(capability)
    row = await _get_row(db, user.id, capability)
    if row is not None:
        await db.delete(row)
        await db.commit()
    if capability in ("text", "vision"):
        api_client.remove_user_adapter(user.id, capability)
    return {"ok": True, "configured": False}


# ---------------------------------------------------------------- 连接测试

class ProviderTestIn(BaseModel):
    capability: str
    provider: str
    base_url: str = ""
    model: str = ""
    secret: dict[str, str] = {}
    options: dict[str, str] = {}


def _tts_ctx_from(provider: str, secret: dict, options: dict, model: str = ""):
    from app.core.podcast_tts import TTSContext
    p = (provider or "edge").strip().lower()
    return TTSContext(
        provider=p,
        voice_a=(options or {}).get("voice_a") or None,
        voice_b=(options or {}).get("voice_b") or None,
        volc_app_id=(secret or {}).get("app_id") or None,
        volc_access_token=(secret or {}).get("access_token") or None,
        volc_cluster=(options or {}).get("cluster") or None,
        azure_key=(secret or {}).get("api_key") or None,
        azure_region=(options or {}).get("region") or None,
    )


async def _run_test(capability: str, provider: str, base_url: str, model: str,
                    secret: dict, options: dict, user_id: str) -> dict:
    """真发一次请求验证这一档能用。失败抛 HTTPException(400)。

    - text  ：短对话，校验非空
    - vision：**发真图**（1x1 PNG），证明该模型确实接受图片
    - tts   ：合成一句短话，把音频回给前端直接试听
    """
    if capability == "tts":
        from app.core.podcast_tts import (
            TTSNotConfiguredError, TTSError, synthesize_text,
        )
        try:
            audio = await synthesize_text("你好，这是一句试听。", speed=1.0,
                                          tts_ctx=_tts_ctx_from(provider, secret, options, model))
        except TTSNotConfiguredError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except TTSError as e:
            raise HTTPException(status_code=400, detail=f"合成失败：{str(e)[:160]}")
        return {"ok": True, "message": f"合成成功（{len(audio)} 字节）",
                "sample_audio_b64": base64.b64encode(audio).decode()}

    # text / vision 走临时适配器，finally 清理，绝不留在注册表里
    tmp_id = f"t{user_id}"
    api_key = (secret or {}).get("api_key", "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="请填写 API Key")
    try:
        api_client.configure_user_adapter(tmp_id, api_key, base_url or None, model or None,
                                          capability=capability, provider=provider)
        adapter = api_client.get_adapter(model or provider, user_id=tmp_id, capability=capability)
        if capability == "vision":
            content = [
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{_TEST_PNG_B64}", "detail": "low"}},
                {"type": "text", "text": "这张图是什么颜色？一个词回答。"},
            ]
        else:
            content = "你好，请只回复：OK"
        resp = await adapter.chat_completion(
            [{"role": "user", "content": content}],
            AdapterConfig(temperature=0.1, max_tokens=32, timeout=25),
        )
        if not (resp.content or "").strip():
            raise RuntimeError("返回为空")
        msg = "连接成功" if capability == "text" else "连接成功，模型可读图"
        return {"ok": True, "message": msg, "reply": (resp.content or "").strip()[:100]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"连接失败：{str(e)[:160]}")
    finally:
        api_client.remove_user_adapter(tmp_id, capability)


@router.post("/providers/test")
async def test_provider(data: ProviderTestIn, user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    """测试一档配置能否用（可带已存的凭据：secret 留空则用库里已存的）。"""
    _check_capability(data.capability)
    provider = (data.provider or "").strip()
    if not find_preset(data.capability, provider):
        raise HTTPException(status_code=400, detail=f"「{data.capability}」档不支持服务商「{provider}」")
    row = await _get_row(db, user.id, data.capability)
    existing = decrypt_secret(row.secret_encrypted, owner=f"{user.id}/{data.capability}") \
        if row and row.secret_encrypted else {}
    secret = _merge_secret(existing, data.secret)
    options = {**(load_options(row) if row else {}), **(data.options or {})}
    _require_fields(data.capability, provider, secret)
    return await _run_test(data.capability, provider, (data.base_url or "").strip(),
                           (data.model or "").strip(), secret, options, user.id)


class ModelListIn(BaseModel):
    provider: str
    base_url: str = ""
    secret: dict[str, str] = {}


@router.post("/providers/models")
async def list_models(data: ModelListIn, user: User = Depends(get_current_user)):
    """拉取服务商的模型列表（服务端代拉：不让 Key 从浏览器直连第三方）。

    **失败一律降级**为 supported=false —— 拉不到列表不是错误，用户手填即可。
    """
    import httpx
    base_url = (data.base_url or "").strip().rstrip("/")
    api_key = (data.secret or {}).get("api_key", "").strip()
    if not base_url:
        return {"supported": False, "models": [], "hint": "请先填写接口地址"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{base_url}/models",
                                    headers={"Authorization": f"Bearer {api_key}"})
        items = (resp.json() or {}).get("data") or []
        models = sorted({str(i.get("id")) for i in items if isinstance(i, dict) and i.get("id")})
        if not models:
            return {"supported": False, "models": [],
                    "hint": "该服务未返回模型列表，请手动填写模型名"}
        return {"supported": True, "models": models}
    except Exception as e:  # noqa: BLE001
        logger.info("拉取模型列表失败 provider=%s: %s", data.provider, e)
        return {"supported": False, "models": [],
                "hint": "该服务未提供模型列表，请手动填写模型名"}


# ---------------------------------------------------------------- 旧端点（过渡 shim）

# 旧版只有一个「单 Key 三元组」。前端可能被缓存、mobile/ 仍在调用，
# 所以保留这四个端点，一律**委托到 text 档**，不再写 users.api_key_* 旧列。
# 下个版本再删。


class ApiKeyIn(BaseModel):
    api_key: str
    base_url: str = ""
    model: str = ""


@router.get("/apikey", deprecated=True)
async def get_apikey(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """[已弃用] 用「文本」档。"""
    d = _describe(await _get_row(db, user.id, "text"), "text")
    return {"configured": d["configured"], "masked_key": d["masked_key"],
            "base_url": d["base_url"], "model": d["model"]}


@router.put("/apikey", deprecated=True)
async def save_apikey(data: ApiKeyIn, user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    """[已弃用] 等价于 PUT /providers/text。"""
    return await save_provider("text", ProviderConfigIn(
        provider="deepseek", base_url=data.base_url, model=data.model,
        secret={"api_key": data.api_key}), user, db)


@router.delete("/apikey", deprecated=True)
async def delete_apikey(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """[已弃用] 等价于 DELETE /providers/text。"""
    return await delete_provider("text", user, db)


@router.post("/apikey/test", deprecated=True)
async def test_apikey(data: ApiKeyIn, user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    """[已弃用] 等价于 POST /providers/test（text 档）。"""
    return await test_provider(ProviderTestIn(
        capability="text", provider="deepseek", base_url=data.base_url, model=data.model,
        secret={"api_key": data.api_key}), user, db)
