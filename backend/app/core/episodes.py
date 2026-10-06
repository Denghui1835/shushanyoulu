"""Episode（一讲）的规划与生成。

一讲 = 本章内一段连续阅读单元（页/块）。章太短就是一讲，章太长按字数预算切成 N 讲——
本机语料里最大的章有 84 页、还有 469 页的整书，不切的话「一期音频」会是一个多小时。

生成复用 P1 的内容寻址缓存（`listen_tts.cache_key` / `store_cache`）：
同一段文本 + 同音色语速 → 同一个 hash，所以**平台预置精品课只合成一次，之后 N 个人听同一份文件**。
Episode 行只是把「讲名、时间轴、进度、断点」这些**属于用户侧**的东西记下来。
"""
import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.listen_tts import (
    cache_key,
    load_cached,
    split_sentences,
    store_cache,
    synthesize_unit_read,
)
from app.core.podcast_tts import _resolve_provider, resolve_tts_context
from app.core.reading_content import get_reading_units
from app.models import Document, Episode

logger = logging.getLogger("yuanqi.episodes")

# 一讲的正文字数预算：约 9000 字 ≈ 30 分钟音频（中文 TTS ~5 字/秒）
EPISODE_MAX_CHARS = 9000
# 生成中的行若超过这么久没动静，视为进程中断（重启/崩溃），允许重新生成
STALE_RUNNING_SECONDS = 180


def plan_spans(units: list[dict], max_chars: int = EPISODE_MAX_CHARS) -> list[dict]:
    """把一章的阅读单元切成若干讲（在单元边界切，不切开一页）。

    每项: {seq, span_start, span_end, title_hint, char_count}
    单页就超过预算时该页独占一讲——宁可超预算，也不能把一页切成两半。
    """
    if not units:
        return []

    spans: list[dict] = []
    start_idx = 0
    cur_chars = 0

    def flush(end_idx: int, seq: int) -> None:
        chunk = units[start_idx:end_idx + 1]
        spans.append({
            "seq": seq,
            "span_start": chunk[0]["index"],
            "span_end": chunk[-1]["index"],
            "title_hint": _span_title(chunk),
            "char_count": sum(len(u.get("text") or "") for u in chunk),
        })

    for i, u in enumerate(units):
        n = len(u.get("text") or "")
        # 已经装了东西，再装这一页会超预算 → 先收一讲（本页留给下一讲）
        if cur_chars and cur_chars + n > max_chars:
            flush(i - 1, len(spans))
            start_idx, cur_chars = i, 0
        cur_chars += n
    flush(len(units) - 1, len(spans))
    return spans


def _span_title(chunk: list[dict]) -> str:
    """一讲的显示名：单页就用页名，多页给「首页 – 末页」。"""
    first = (chunk[0].get("title") or "").strip()
    last = (chunk[-1].get("title") or "").strip()
    if not first:
        return ""
    if len(chunk) == 1 or first == last:
        return first
    return f"{first} – {last}"


def episode_title(doc: Document, span: dict, total: int) -> str:
    """整章的显示名。一章一讲就用章名，切过就带「第 k 讲」。"""
    base = (doc.chapter_title or doc.title or "未命名").strip()
    if total <= 1:
        return base[:256]
    hint = span.get("title_hint") or ""
    return (f"{base} · 第 {span['seq'] + 1} 讲" + (f"（{hint}）" if hint else ""))[:256]


async def get_or_create_episodes(db: AsyncSession, doc: Document, user_id: str,
                                 kind: str = "read", voice: str = "",
                                 speed: float = 1.0) -> list[Episode]:
    """取（不存在则规划并落库）某章的讲列表。幂等：同一区间不会重复建。

    音色/语速变了不新建讲——同一讲的音频按内容寻址另存一份，讲本身还是那一讲
    （否则用户换个音色，播放列表里就凭空多出一整套）。
    """
    units = await get_reading_units(db, doc)
    if not units:
        return []

    spans = plan_spans(units)
    existing = (await db.execute(
        select(Episode).where(Episode.document_id == doc.id, Episode.kind == kind)
        .order_by(Episode.seq)
    )).scalars().all()

    by_span = {(e.span_start, e.span_end): e for e in existing}
    # 建档时就记下「按谁的语音档生成」，这样后台任务与缓存键才能一致
    tts_ctx = await resolve_tts_context(db, user_id)
    out: list[Episode] = []
    created = False
    for span in spans:
        key = (span["span_start"], span["span_end"])
        ep = by_span.get(key)
        if ep is None:
            ep = Episode(
                project_id=doc.project_id or "", document_id=doc.id, user_id=user_id,
                kind=kind, span_start=span["span_start"], span_end=span["span_end"],
                seq=span["seq"], title=episode_title(doc, span, len(spans)),
                provider=_resolve_provider(tts_ctx), voice=voice, speed=speed,
            )
            db.add(ep)
            created = True
            out.append(ep)
        else:
            out.append(ep)
    if created:
        await db.commit()
        for ep in out:
            await db.refresh(ep)
    return out


async def build_source(db: AsyncSession, doc: Document, ep: Episode) -> tuple[str, list[str], list[int]]:
    """拼一讲的正文。

    返回 (全文, 逐句, 每句来自哪一页)。**逐页分别断句再拼接**，而不是把整章拼成
    一大段再断——这样每个句子都能反查回它所在的页，「点句子 → 去阅读页」才成立。
    """
    units = await get_reading_units(db, doc)
    lo, hi = ep.span_start, ep.span_end
    picked = [u for u in units
              if u["index"] >= lo and (hi is None or u["index"] <= hi)]

    sentences: list[str] = []
    units_of: list[int] = []
    for u in picked:
        for s in split_sentences(u.get("text") or ""):
            sentences.append(s)
            units_of.append(u["index"])
    return "\n".join(sentences), sentences, units_of


def source_key(text: str, voice: str, speed: float, provider: str) -> str:
    """一讲的内容哈希——直接用 listen_tts 的缓存键，好让页级 prepare 与讲级共用同一份音频。"""
    return cache_key(text, voice, speed, provider)


async def _mark(db: AsyncSession, ep: Episode, **fields) -> None:
    for k, v in fields.items():
        setattr(ep, k, v)
    await db.commit()


async def generate_episode(episode_id: str) -> None:
    """生成一讲的音频与时间轴（独立任务，**不挂在 HTTP 连接上**）。

    由 api/listen.py 用 asyncio.create_task 拉起，所以关掉页面/断网都不会中断生成；
    SSE 端点只是轮询数据库里的 progress_* 把进度转述出去。
    """
    from app.database import async_session

    async with async_session() as db:
        ep = await db.get(Episode, episode_id)
        if ep is None:
            logger.warning("生成任务找不到讲 %s", episode_id)
            return
        doc = await db.get(Document, ep.document_id)
        if doc is None:
            await _mark(db, ep, status="error", error="章节不存在")
            return

        text, sentences, units_of = await build_source(db, doc, ep)
        if not sentences:
            await _mark(db, ep, status="error", error="这一讲没有可朗读的正文（可能是扫描图片页）")
            return

        # 用讲所属用户自己的语音档：provider 进了缓存键，所以同一个用户在
        # edge 与豆包之间切换会各存各的音频，不会互相串。
        tts_ctx = await resolve_tts_context(db, ep.user_id)
        provider = _resolve_provider(tts_ctx)
        voice = ep.voice or ""
        speed = ep.speed or 1.0
        key = source_key(text, voice, speed, provider)

        # 命中内容寻址缓存 → 别人已经生成过同一段（预置课/同好），直接复用
        hit = load_cached(key)
        if hit and not (hit[1].get("failed_segments") or []):
            _, timeline = hit
            logger.info("讲 %s 命中音频缓存 %s，跳过合成", episode_id, key)
            await _mark(db, ep, status="done", error="", source_hash=key, audio_hash=key,
                        audio_seconds=float(timeline.get("duration") or 0),
                        timeline=json.dumps(timeline, ensure_ascii=False),
                        progress_done=ep.progress_total, progress_total=ep.progress_total)
            return

        await _mark(db, ep, status="running", error="", source_hash=key,
                    progress_done=0, progress_total=0)

        async def on_progress(done: int, total: int) -> None:
            # 每段落一次盘：SSE 端点靠它转述进度，进程被打断也能看出停在哪
            await _mark(db, ep, progress_done=done, progress_total=total)

        try:
            audio, timeline = await synthesize_unit_read(
                text, voice=voice, speed=speed,
                sentences=sentences, on_progress=on_progress, tts_ctx=tts_ctx)
        except Exception as e:  # noqa: BLE001
            logger.exception("讲 %s 合成失败", episode_id)
            await _mark(db, ep, status="error", error=str(e)[:300])
            return

        # 每句标注它来自哪一页，前端「去阅读页」用
        timeline["sentence_units"] = units_of
        store_cache(key, audio, timeline)
        failed = timeline.get("failed_segments") or []
        await _mark(
            db, ep,
            status="done",
            error=(f"{len(failed)} 段合成失败，对应句子无高亮" if failed else ""),
            audio_hash=key,
            audio_seconds=float(timeline.get("duration") or 0),
            timeline=json.dumps(timeline, ensure_ascii=False),
            progress_done=ep.progress_total, progress_total=ep.progress_total,
        )
        logger.info("讲 %s 生成完成：%.1fs，%d 句", episode_id,
                    timeline.get("duration") or 0, len(timeline.get("sentences") or []))


def is_stale(ep: Episode) -> bool:
    """生成中的讲是不是「卡死了」（还挂着 running 但早就不动了）。

    主要判据其实是任务登记表（见 api/listen.py 的 `_tasks`）：进程重启后表是空的，
    所以「status=running 但没有活着的任务」= 崩溃留下的孤儿，重来即可。
    这里的超时只是**回答不了登记表时**的兜底（比如任务活着但卡在某个网络调用上）。

    时间戳必须按 **UTC** 比：created_at/updated_at 是 `server_default=func.now()`，
    SQLite 的 CURRENT_TIMESTAMP 给的是 UTC；拿本地 datetime.now() 去减会差出一个
    时区（本机 +8），180 秒的阈值会被恒定判成「早就过期了」。
    """
    if ep.status != "running":
        return False
    ts = ep.updated_at or ep.created_at
    if ts is None:
        return True
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    return now_utc - ts > timedelta(seconds=STALE_RUNNING_SECONDS)


def episode_timeline(ep: Episode) -> dict:
    if not ep.timeline:
        return {}
    try:
        return json.loads(ep.timeline)
    except json.JSONDecodeError:
        logger.warning("讲 %s 的时间轴 JSON 损坏", ep.id)
        return {}