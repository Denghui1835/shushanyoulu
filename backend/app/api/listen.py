"""听读 API —— 原文逐句朗读 + 逐句时间轴（「听带读」）。

页级端点（P1 纵向切片，仍在用）：
- GET  /api/listen/status   某文档各阅读单元的音频就绪情况
- POST /api/listen/prepare  准备某单元的朗读音频（命中缓存秒回）
- GET  /api/listen/audio    流式返回音频（支持 Range）

讲级端点（P2 Episode 化，主界面走这条）：
- GET  /api/listen/album            整本书 → 章 → 讲的目录（**只查库，不解析 PDF**）
- GET  /api/listen/episodes         某章有哪些讲（不存在则按字数预算规划并落库）
- POST /api/listen/episodes/{id}/generate  开始生成（202，任务脱离 HTTP 连接）
- GET  /api/listen/episodes/{id}/events    SSE 报进度直到生成完
- GET  /api/listen/episodes/{id}/audio     Range 流
- GET  /api/listen/episodes/{id}           详情（含逐句时间轴）
- PUT  /api/listen/episodes/{id}/progress  断点续听
- GET  /api/listen/continue                上次听到哪儿了

为什么生成要脱离请求：一讲 ~9000 字 ≈ 45 段 edge 合成 ≈ 一分半，同步请求扛不住，
而且关掉页面/断网不该把生成打断。
"""
import asyncio
import json
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.podcast import _serve_audio_range
from app.core.access import get_owned_project, get_readable_document
from app.core.auth import get_optional_user
from app.core.episodes import (
    episode_timeline,
    generate_episode,
    get_or_create_episodes,
    is_stale,
)
from app.core.listen_tts import (
    cache_key,
    cache_paths,
    load_cached,
    split_sentences,
    store_cache,
    synthesize_unit_read,
)
from app.core.podcast_tts import (
    TTSNotConfiguredError,
    TTSError,
    TTSContext,
    _resolve_provider,
    _voice_for,
    _SPEAKER_A,
    resolve_tts_context,
)
from app.core.reading_content import get_reading_units
from app.database import get_db
from app.models import Document, Episode, PlaybackProgress, User

logger = logging.getLogger("yuanqi.api.listen")
router = APIRouter(prefix="/api/listen", tags=["listen"])


class PrepareIn(BaseModel):
    document_id: str
    unit_index: int = 0
    voice: str | None = None
    speed: float = 1.0


async def _resolve_unit(db: AsyncSession, document_id: str, unit_index: int,
                        user: User | None) -> tuple[Document, str, str]:
    """校验读权限并取某阅读单元的正文。返回 (doc, text, title)。"""
    doc = await get_readable_document(db, document_id, user)
    units = await get_reading_units(db, doc)
    for u in units:
        if u["index"] == unit_index:
            return doc, (u.get("text") or ""), (u.get("title") or "")
    raise HTTPException(status_code=404, detail=f"阅读单元 {unit_index} 不存在")


async def _tts_ctx_for(db: AsyncSession, user: User | None) -> TTSContext:
    """取当前用户的语音档（未登录/未配置 → 回落全局，通常是免费的 edge）。

    **所有**听读端点都必须用它解析 provider，因为 provider 进了缓存键：
    同一段文字在 edge 和豆包下是两份不同的音频文件，用错 provider 就找不到文件。
    """
    return await resolve_tts_context(db, user.id if user else None)


def _default_voice(tts_ctx: TTSContext | None = None) -> str:
    return _voice_for(_resolve_provider(tts_ctx), _SPEAKER_A, tts_ctx)


# ---------------------------------------------------------------- 就绪状态

@router.get("/status")
async def listen_status(document_id: str, voice: str | None = None, speed: float = 1.0,
                        db: AsyncSession = Depends(get_db),
                        user: User | None = Depends(get_optional_user)):
    """各阅读单元的音频就绪情况。

    注意：这里为了算缓存键会重新解析一次阅读单元（PDF 要再抽一次文本）。
    跟 /api/reading/{id}/content 那次解析是重复的——P2 换成 episodes 表之后
    就变成一次数据库查询了，届时删掉这个端点里的解析。
    """
    doc = await get_readable_document(db, document_id, user)
    tts_ctx = await _tts_ctx_for(db, user)
    provider = _resolve_provider(tts_ctx)
    v = voice or _default_voice(tts_ctx)
    units = await get_reading_units(db, doc)

    items = []
    for u in units:
        text = u.get("text") or ""
        key = cache_key(text, v, speed, provider)
        cached = load_cached(key)
        failed = len((cached[1].get("failed_segments") or [])) if cached else 0
        items.append({
            "index": u["index"],
            "unit_type": u.get("unit_type"),
            "title": u.get("title") or f"第 {u['index'] + 1} 单元",
            "char_count": len(text),
            "sentence_count": len(split_sentences(text)),
            "ready": cached is not None,
            # 部分段失败的缓存虽然能播，但不是「备好了」——列表上要能看出来
            "failed_segments": failed,
            "partial": failed > 0,
            "duration": round(cached[1].get("duration") or 0, 1) if cached else None,
        })
    return {
        "document_id": document_id,
        "title": doc.title,
        "provider": provider,
        "voice": v,
        "speed": speed,
        "units": items,
        "ready_count": sum(1 for i in items if i["ready"]),
    }


# ---------------------------------------------------------------- 准备音频

@router.post("/prepare")
async def listen_prepare(data: PrepareIn, db: AsyncSession = Depends(get_db),
                         user: User | None = Depends(get_optional_user)):
    """把某阅读单元做成「原文朗读音频 + 逐句时间轴」。命中缓存则直接返回（cached=true）。"""
    doc, text, title = await _resolve_unit(db, data.document_id, data.unit_index, user)
    if not text.strip():
        raise HTTPException(status_code=400, detail="这一页没有可朗读的正文（可能是扫描图片页）")

    tts_ctx = await _tts_ctx_for(db, user)
    provider = _resolve_provider(tts_ctx)
    voice = data.voice or _default_voice(tts_ctx)
    speed = data.speed or 1.0
    key = cache_key(text, voice, speed, provider)

    hit = load_cached(key)
    # 缓存带「失败段」时不当命中，重生成一次并覆盖缓存（自愈）。
    # 原先是一律命中——一旦某段合成失败就被永久钉在缓存里（已验证：
    # 两次 prepare 都在 0.03s 返回同一份 failed=[0]），那几句永远没声音，
    # 只能靠 DELETE /api/listen/cache 把**所有**好缓存一起清掉才有救。
    # 失败的音频仍然照常落盘：用户至少还能听到成功的那几句。
    if hit and not (hit[1].get("failed_segments") or []):
        audio, timeline = hit
        cached = True
    else:
        if hit:
            logger.info("听读缓存含失败段，重生成 doc=%s unit=%s key=%s",
                        data.document_id, data.unit_index, key)
        try:
            audio, timeline = await synthesize_unit_read(text, voice=voice, speed=speed,
                                                         tts_ctx=tts_ctx)
        except TTSNotConfiguredError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except TTSError as e:
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:  # noqa: BLE001
            logger.exception("听读合成失败 doc=%s unit=%s", data.document_id, data.unit_index)
            raise HTTPException(status_code=500, detail=f"朗读合成失败：{str(e)[:200]}")
        store_cache(key, audio, timeline)
        cached = False

    q = f"document_id={data.document_id}&unit_index={data.unit_index}&voice={voice}&speed={speed}"
    return {
        "document_id": data.document_id,
        "unit_index": data.unit_index,
        "title": title or doc.title,
        "cached": cached,
        "provider": provider,
        "voice": voice,
        "duration": timeline.get("duration"),
        "failed_segments": timeline.get("failed_segments") or [],
        "sentences": timeline.get("sentences") or [],
        "audio_url": f"/api/listen/audio?{q}",
    }


# ---------------------------------------------------------------- 音频流

@router.get("/audio")
async def listen_audio(document_id: str, request: Request, unit_index: int = 0,
                       voice: str | None = None, speed: float = 1.0,
                       db: AsyncSession = Depends(get_db),
                       user: User | None = Depends(get_optional_user)):
    """流式返回朗读音频，支持 Range（拖进度条必需）。未 prepare 过则 404。"""
    _doc, text, _title = await _resolve_unit(db, document_id, unit_index, user)
    tts_ctx = await _tts_ctx_for(db, user)
    provider = _resolve_provider(tts_ctx)
    v = voice or _default_voice(tts_ctx)
    key = cache_key(text, v, speed or 1.0, provider)

    audio_path, _json_path = cache_paths(key)
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="音频还没准备好，请先调用 prepare")
    return _serve_audio_range(audio_path, "audio/mpeg", request)


@router.delete("/cache")
async def clear_listen_cache(document_id: str | None = None):
    """清空听读音频缓存（调试/换音色后想强制重生成时用）。

    缓存是内容寻址的：清了不会丢课程内容，下次 prepare 会重新生成。
    """
    from app.core.listen_tts import _cache_dir
    d = _cache_dir()
    removed = 0
    if d.is_dir():
        for p in d.glob("*.mp3"):
            try:
                p.unlink()
                removed += 1
            except Exception as e:  # noqa: BLE001
                logger.warning("删除缓存失败 %s: %s", p, e)
        for p in d.glob("*.json"):
            try:
                p.unlink()
            except Exception:
                pass
    return {"ok": True, "removed": removed}


# ================================================================ 讲（Episode）

class ProgressIn(BaseModel):
    position_ms: int = 0
    finished: bool = False


# 正在跑的生成任务：同一讲不重复拉起（两次点击 / SSE 重连都可能再 POST 一次）
_tasks: dict[str, asyncio.Task] = {}


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _ready(ep: Episode) -> bool:
    """音频是不是真的能播——光看 status 不够，文件可能被清理掉了。"""
    if ep.status != "done" or not ep.audio_hash:
        return False
    return cache_paths(ep.audio_hash)[0].exists()


def _episode_dict(ep: Episode, prog: PlaybackProgress | None = None,
                  with_timeline: bool = False) -> dict:
    tl = episode_timeline(ep)
    out = {
        "id": ep.id,
        "document_id": ep.document_id,
        "project_id": ep.project_id,
        "kind": ep.kind,
        "seq": ep.seq,
        "title": ep.title,
        "span_start": ep.span_start,
        "span_end": ep.span_end,
        "status": ep.status,
        "error": ep.error or "",
        "duration": round(ep.audio_seconds or 0, 1),
        "sentence_count": len(tl.get("sentences") or []),
        "ready": _ready(ep),
        "failed_segments": len(tl.get("failed_segments") or []),
        "progress_done": ep.progress_done or 0,
        "progress_total": ep.progress_total or 0,
        "position_ms": prog.position_ms if prog else 0,
        "finished": bool(prog.finished) if prog else False,
    }
    if out["ready"]:
        out["audio_url"] = f"/api/listen/episodes/{ep.id}/audio"
    if with_timeline:
        out["sentences"] = tl.get("sentences") or []
        out["sentence_units"] = tl.get("sentence_units") or []
    return out


async def _load_episode(db: AsyncSession, episode_id: str, user: User | None) -> Episode:
    """取一讲并校验它所属章节的读权限。"""
    ep = await db.get(Episode, episode_id)
    if not ep:
        raise HTTPException(status_code=404, detail="这一讲不存在")
    await get_readable_document(db, ep.document_id, user)
    return ep


async def _progress_map(db: AsyncSession, user: User | None,
                        episode_ids: list[str]) -> dict[str, PlaybackProgress]:
    if not episode_ids:
        return {}
    from app.core.access import owner_id
    rows = (await db.execute(
        select(PlaybackProgress).where(
            PlaybackProgress.user_id == owner_id(user),
            PlaybackProgress.episode_id.in_(episode_ids))
    )).scalars().all()
    return {r.episode_id: r for r in rows}


@router.get("/album")
async def listen_album(project_id: str, kind: str = "read",
                       db: AsyncSession = Depends(get_db),
                       user: User | None = Depends(get_optional_user)):
    """整本书的目录：章 → 讲，附每讲的生成状态与我的进度。

    这个端点**只查数据库、不解析 PDF**：一本书 81 章，逐章解析会读上百个文件。
    讲是点进某一章时才规划的（见 /episodes）。
    """
    proj = await get_owned_project(db, project_id, user, write=False)
    docs = (await db.execute(
        select(Document).where(Document.project_id == project_id)
        .order_by(Document.sort_order, Document.created_at)
    )).scalars().all()
    doc_ids = [d.id for d in docs]

    eps: list[Episode] = []
    if doc_ids:
        eps = (await db.execute(
            select(Episode).where(Episode.document_id.in_(doc_ids), Episode.kind == kind)
            .order_by(Episode.seq)
        )).scalars().all()
    prog = await _progress_map(db, user, [e.id for e in eps])

    by_doc: dict[str, list[Episode]] = {}
    for e in eps:
        by_doc.setdefault(e.document_id, []).append(e)

    chapters = []
    for d in docs:
        items = by_doc.get(d.id, [])
        chapters.append({
            "document_id": d.id,
            "title": d.chapter_title or d.title,
            "content_type": d.content_type,
            "sort_order": d.sort_order,
            "planned": bool(items),
            "episode_count": len(items),
            "done_count": sum(1 for e in items if _ready(e)),
            "episodes": [_episode_dict(e, prog.get(e.id)) for e in items],
        })
    return {
        "project_id": project_id,
        "project_title": proj.title,
        "kind": kind,
        "chapters": chapters,
        "chapter_count": len(chapters),
        "episode_count": len(eps),
        "done_count": sum(1 for e in eps if _ready(e)),
    }


@router.get("/episodes")
async def list_episodes(document_id: str, kind: str = "read",
                        voice: str | None = None, speed: float = 1.0,
                        db: AsyncSession = Depends(get_db),
                        user: User | None = Depends(get_optional_user)):
    """某章有哪些讲。首次调用会按字数预算把这一章切成 N 讲并落库（幂等）。"""
    doc = await get_readable_document(db, document_id, user)
    from app.core.access import owner_id
    eps = await get_or_create_episodes(
        db, doc, owner_id(user), kind=kind,
        voice=voice or _default_voice(), speed=speed or 1.0)
    prog = await _progress_map(db, user, [e.id for e in eps])
    return {
        "document_id": document_id,
        "chapter_title": doc.chapter_title or doc.title,
        "kind": kind,
        "episodes": [_episode_dict(e, prog.get(e.id)) for e in eps],
    }


@router.post("/episodes/{episode_id}/generate")
async def generate_episode_endpoint(episode_id: str,
                                    db: AsyncSession = Depends(get_db),
                                    user: User | None = Depends(get_optional_user)):
    """开始生成音频。**202**：任务在后台跑，进度走 /events。"""
    ep = await _load_episode(db, episode_id, user)

    if _ready(ep):
        return {"episode_id": episode_id, "status": "done", "started": False,
                "audio_url": f"/api/listen/episodes/{episode_id}/audio"}

    running = _tasks.get(episode_id)
    if running is not None and not running.done() and not is_stale(ep):
        return {"episode_id": episode_id, "status": ep.status, "started": False}

    # 已僵死的 running 行（进程重启留下的）→ 直接重来
    task = asyncio.create_task(generate_episode(episode_id))
    _tasks[episode_id] = task
    task.add_done_callback(lambda t: _tasks.pop(episode_id, None))
    return {"episode_id": episode_id, "status": "running", "started": True,
            "events_url": f"/api/listen/episodes/{episode_id}/events"}


@router.get("/episodes/{episode_id}/events")
async def episode_events(episode_id: str,
                         user: User | None = Depends(get_optional_user)):
    """SSE：把生成进度转述给前端，直到 done / error。

    生成任务自己写 episodes.progress_*，这里只是轮询读出来——所以**断线重连不会
    影响生成**，甚至可以在另一个标签页接着看进度。
    """
    from app.database import async_session
    async with async_session() as db:
        ep = await _load_episode(db, episode_id, user)

    async def event_stream():
        deadline = time.monotonic() + 30 * 60
        last = None
        while True:
            async with async_session() as db:
                ep = await db.get(Episode, episode_id)
                if ep is None:
                    yield _sse({"stage": "error", "error": "这一讲不存在"})
                    return
                payload = {
                    "stage": "done" if ep.status == "done" else
                             ("error" if ep.status == "error" else "progress"),
                    "status": ep.status,
                    "done": ep.progress_done or 0,
                    "total": ep.progress_total or 0,
                    "duration": round(ep.audio_seconds or 0, 1),
                    "error": ep.error or "",
                    "audio_url": (f"/api/listen/episodes/{episode_id}/audio"
                                  if _ready(ep) else None),
                }
            # 去重：每段都推一次会把 SSE 撑成噪音（一讲 45 段）
            if payload != last:
                yield _sse(payload)
                last = dict(payload)
            if payload["stage"] in ("done", "error"):
                return
            if time.monotonic() > deadline:
                yield _sse({"stage": "timeout", "error": "生成超时，请重新发起"})
                return
            await asyncio.sleep(0.7)

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@router.get("/episodes/{episode_id}")
async def episode_detail(episode_id: str, db: AsyncSession = Depends(get_db),
                         user: User | None = Depends(get_optional_user)):
    """一讲的详情：含**逐句时间轴**（前端高亮/点句跳转靠它）。"""
    ep = await _load_episode(db, episode_id, user)
    prog = (await _progress_map(db, user, [episode_id])).get(episode_id)
    return _episode_dict(ep, prog, with_timeline=True)


@router.get("/episodes/{episode_id}/audio")
async def episode_audio(episode_id: str, request: Request,
                        db: AsyncSession = Depends(get_db),
                        user: User | None = Depends(get_optional_user)):
    """一讲的音频，支持 Range（拖进度条必需）。"""
    ep = await _load_episode(db, episode_id, user)
    if not ep.audio_hash:
        raise HTTPException(status_code=404, detail="这一讲还没生成音频")
    audio_path, _ = cache_paths(ep.audio_hash)
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="音频文件已丢失，请重新生成")
    return _serve_audio_range(audio_path, "audio/mpeg", request)


@router.put("/episodes/{episode_id}/progress")
async def save_progress(episode_id: str, data: ProgressIn,
                        db: AsyncSession = Depends(get_db),
                        user: User | None = Depends(get_optional_user)):
    """记下听到哪儿了（断点续听）。同一讲只留一行。"""
    from app.core.access import owner_id
    ep = await _load_episode(db, episode_id, user)
    uid = owner_id(user)

    row = (await db.execute(
        select(PlaybackProgress).where(
            PlaybackProgress.user_id == uid,
            PlaybackProgress.episode_id == episode_id)
    )).scalar_one_or_none()
    if row is None:
        row = PlaybackProgress(user_id=uid, episode_id=episode_id,
                               document_id=ep.document_id)
        db.add(row)
    row.position_ms = max(0, int(data.position_ms or 0))
    row.finished = 1 if data.finished else 0
    await db.commit()
    return {"ok": True, "episode_id": episode_id,
            "position_ms": row.position_ms, "finished": bool(row.finished)}


@router.get("/continue")
async def continue_listening(project_id: str | None = None,
                             db: AsyncSession = Depends(get_db),
                             user: User | None = Depends(get_optional_user)):
    """上次听到哪儿了——「继续收听」入口。

    只挑没听完的；听完的讲不再拦在入口上（否则永远停在同一个地方）。
    """
    from app.core.access import owner_id
    q = (select(PlaybackProgress, Episode)
         .join(Episode, Episode.id == PlaybackProgress.episode_id)
         .where(PlaybackProgress.user_id == owner_id(user),
                PlaybackProgress.finished == 0,
                PlaybackProgress.position_ms > 0)
         .order_by(PlaybackProgress.updated_at.desc()).limit(20))
    if project_id:
        q = q.where(Episode.project_id == project_id)

    out = []
    for prog, ep in (await db.execute(q)).all():
        try:
            await get_readable_document(db, ep.document_id, user)
        except HTTPException:
            continue
        item = _episode_dict(ep, prog)
        item["updated_at"] = prog.updated_at.isoformat() if prog.updated_at else None
        out.append(item)
        if len(out) >= 10:
            break
    return {"items": out}