"""听读（原文逐句朗读）—— 逐句时间轴 + 内容寻址缓存。

跟 AI 播客（podcast_tts）的区别：
- 播客是「双主播对谈」：别人替你消化，听着爽，但注意力离开了原文；
- 这里（read 模式）是**原文逐句朗读**，一字不改，配上逐句高亮才能做到
  「听是主线、读跟着走」——通勤/走路/睡前都能学，又不至于听个热闹。

时间轴怎么来的（provider 无关，零新增依赖）：
逐段合成 → 用 mutagen 单独测每段时长 → 累加得到每段的 [start, end)，
段内再按各句字数把段时长**按比例分摊**给句子 → 逐句时间轴。

诚实的精度说明：分摊是近似。中文里标点、数字、英文字母的发音耗时跟字数并不成正比，
所以**段内**的逐句时间可能有 ±0.3~0.8s 偏差；**段与段之间是实测的，不累积漂移**。
对「高亮跟着走 + 点句跳转」够用。要词级精度得用 edge-tts 的 boundary 事件
（7.2.8 确实有这个参数），那是后续增强，不是本模块的依赖。
"""
import asyncio
import hashlib
import json
import logging
import re
import wave
from io import BytesIO
from pathlib import Path

from app.config import settings
from app.core.podcast_tts import (
    _EDGE_REQUEST_INTERVAL,
    _READ_PAUSE,
    _READ_PITCH_CYCLE,
    _SPEAKER_A,
    TTSError,
    TTSContext,
    _edge_synthesize,
    _expected_speech_seconds,
    _mp3_bytes_duration_estimate,
    _resolve_provider,
    _synthesize,
    _validate_coverage,
    _voice_for,
)

logger = logging.getLogger("yuanqi.listen_tts")

TIMELINE_VERSION = 4

# 断句：句末标点/换行后切，**保留标点本身**（切点自带标点，拼回去就是原文）
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？；!?;\n])")
# 是否含「实词字符」：用来剔除纯符号片段（见 split_sentences）
_WORDISH_RE = re.compile(r"[0-9A-Za-z一-鿿]")

# markdown 语法标记：送 TTS 前要清掉（见 speakable）
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")          # [文字](url) → 文字
_MD_TABLE_SEP_RE = re.compile(r"^\s*\|[\s:|-]*\|\s*$")      # | --- | :--: | 整行
_MD_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s*", re.M)     # ## 标题
_MD_BULLET_RE = re.compile(r"^\s{0,3}(?:[-*+]|\d+[.)])\s+", re.M)  # - 项 / 1. 项
_MD_EMPH_RE = re.compile(r"(\*\*|__|~~|[*_`])")             # 加粗/斜体/删除线/反引号
# 「不发音的符号」成串出现时抹掉：---、|、**、#、> 之类 TTS 不会念成时间的字符。
# 为什么不能只靠上面那些按**行**写的规则：split_sentences 是按 \n 切再 strip 的，
# 轮到 speakable 时行结构早就没了——实测 `| 题型 | 分值 |` 和 `| --- | --- |`
# 被粘成一句，`--- --- ---` 就这么念了出去（而且它占字数却几乎不占音频时长，
# 正是把「预期 25.8s / 实际 17.2s」压到误判截断的元凶）。所以这里按**内容**兜底。
_NON_SPEECH_RE = re.compile(r"[-_=*#|~`<>]{1,}")


def speakable(text: str) -> str:
    """把 markdown 原文转成「念出来是人话」的文本 —— 送 TTS 用它，**显示仍用原文**。

    为什么必须做这一步：`_edge_synthesize` 有一道防截断闸门，它按
    `len(text)/4.5` 预估音频时长，实测短于预期的 70% 就判定「服务端截断」并抛错。
    可 markdown 表格里全是 TTS 根本不发音的字符（`|`、`---`、`#`），于是
    144 字的表格「预期 32 秒、实际 19.2 秒」→ 闸门误判 → **整段被丢弃**。
    实测：`## 考试结构` 那一页的表格句全部静音，且因为是确定性失败，
    每次重生成都失败。这不是截断，是喂错了东西。

    只动**语法标记**，正文一个字都不改：不念「井号井号」，不念表格竖线、
    不念 `---` 分隔行、不念加粗星号/反引号/链接地址。正文照旧完整显示在页面上。
    """
    t = text or ""
    t = _MD_LINK_RE.sub(r"\1", t)
    # 整行的表格分隔行直接删掉（它是给渲染器看的，念出来只有噪音）
    t = "\n".join(l for l in t.splitlines() if not _MD_TABLE_SEP_RE.match(l))
    t = t.replace("|", " ")          # 单元格竖线 → 空格，念起来自然断句
    t = _MD_HEADING_RE.sub("", t)
    t = _MD_BULLET_RE.sub("", t)
    t = _MD_EMPH_RE.sub("", t)
    t = _NON_SPEECH_RE.sub(" ", t)   # 兜底：剩下的成串不发音符号（见上面的说明）
    return re.sub(r"\s{2,}", " ", t).strip()


def _speak_len(text: str) -> int:
    """一句原文「念出来有多少字」——用于段内时长分摊的权重。

    取 speakable 后的长度，但**至少按 1 算**：万一某句清完标记什么都不剩
    （纯 `---` 之类），给它 0 权重会让它和相邻句的时间重叠、高亮闪一下就没。
    """
    return max(1, len(speakable(text)))
# 一个 TTS 段最多多少字：太长语调发平像念经，太短调用次数爆炸（edge 会限流）
_GROUP_MAX_CHARS = 180


def _rate_for(speed: float) -> str:
    """1.0 → '+0%'；edge 的 rate 参数格式。"""
    pct = int(round((speed - 1.0) * 100))
    return f"+{pct}%" if pct >= 0 else f"{pct}%"


def normalize_for_hash(text: str) -> str:
    """算缓存键前把空白抹平：同一页文本从 PDF 抽取时换行/空格会抖动，
    但朗读结果几乎不受影响，所以按「无空白」归一化以提高命中率。

    注意：只用于**算 hash**。真正送进 TTS 的仍是原文（含原始空白）。
    """
    return re.sub(r"\s+", "", text or "")


def split_sentences(text: str) -> list[str]:
    """把正文切成句子（保留句末标点）。逐句高亮/点句跳转的粒度就是它。

    纯符号片段（"•"、"-"、"·" 这类项目符号，或被换行切出来的孤立标点）不单独成句——
    它既会白跑一次 TTS，高亮时也只是闪一个点。直接并进相邻句子里。
    """
    parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(text or "") if p.strip()]
    out: list[str] = []
    pending = ""
    for p in parts:
        if not _WORDISH_RE.search(p):
            if out:
                out[-1] += p
            else:
                pending += p
            continue
        out.append(pending + p)
        pending = ""
    if pending:
        if out:
            out[-1] += pending
        else:
            out.append(pending)
    return out


def _group_sentences(sentences: list[str]) -> list[list[str]]:
    """把相邻句子并成不超过 _GROUP_MAX_CHARS 的 TTS 段（少调用几次、别被限流）。

    句子本身仍是时间轴的粒度，段只是合成单位。
    """
    groups: list[list[str]] = []
    cur: list[str] = []
    cur_len = 0
    for s in sentences:
        if cur and cur_len + len(s) > _GROUP_MAX_CHARS:
            groups.append(cur)
            cur, cur_len = [], 0
        cur.append(s)
        cur_len += len(s)
    if cur:
        groups.append(cur)
    return groups


def _bytes_duration(data: bytes) -> float | None:
    """估算音频字节时长（秒）。mp3（edge/volc/azure）→ mutagen；wav（mock）→ wave。"""
    d = _mp3_bytes_duration_estimate(data)
    if d:
        return d
    if data[:4] == b"RIFF":
        try:
            with wave.open(BytesIO(data), "rb") as w:
                return w.getnframes() / float(w.getframerate() or 1)
        except Exception:
            return None
    return None


async def synthesize_unit_read(text: str, voice: str | None = None,
                               speed: float = 1.0,
                               sentences: list[str] | None = None,
                               on_progress=None,
                               tts_ctx: TTSContext | None = None) -> tuple[bytes, dict]:
    """原文逐句朗读：返回 (mp3 字节, 时间轴)。

    单段失败不丢整页：失败的段其句子在时间轴里标 start/end = None
    （前端照常显示文字，但不给高亮、不可点跳），并在 failed_segments 里报出。

    `sentences`：调用方已经断好句时直接传进来（一讲跨多页时要**逐页断句再拼**，
    才能知道每句来自哪一页；见 core/episodes.build_source）。不传就按 text 现断。

    `on_progress(done, total)`：每合成完一段回调一次，一讲的 SSE 进度靠它。
    """
    provider = _resolve_provider(tts_ctx)
    voice_name = voice or _voice_for(provider, _SPEAKER_A, tts_ctx)
    rate = _rate_for(speed)

    sentences = sentences if sentences is not None else split_sentences(text)
    if not sentences:
        raise TTSError("这一页没有可朗读的正文")

    groups = _group_sentences(sentences)
    total = len(groups)
    parts: list[bytes] = []
    failed: list[int] = []
    seg_out: list[dict] = []
    sent_out: list[dict] = []
    cursor = 0.0

    for gi, group in enumerate(groups):
        # 送 TTS 的是「可朗读文本」（markdown 标记已清）；句子原文仍按原样留在时间轴里
        spoken = speakable("".join(group)) or "".join(group)
        # 段间追加轻声停顿，让朗读有换气感（跟 podcast_tts 的朗读路径同一套手法）
        if gi < total - 1:
            spoken = spoken.rstrip("。！？!?") + "。" + _READ_PAUSE

        try:
            if provider == "edge":
                pitch = _READ_PITCH_CYCLE[gi % len(_READ_PITCH_CYCLE)]
                audio = await _edge_synthesize(spoken, voice_name, rate=rate, pitch=pitch)
                if gi < total - 1:
                    await asyncio.sleep(_EDGE_REQUEST_INTERVAL)  # 给 edge 服务喘息
            else:
                audio = await _synthesize(provider, spoken, voice_name, ctx=tts_ctx)
        except Exception as e:  # noqa: BLE001
            logger.error("听读第 %d/%d 段合成失败: %s", gi + 1, total, e)
            failed.append(gi)
            first = len(sent_out)
            for s in group:
                sent_out.append({"text": s, "start": None, "end": None})
            # 失败的段也记进 timeline（start/end = None，failed=true）：
            # 否则 segments 里的 i 会跳号，读的人无从分辨「这段没合成」还是「索引错乱」。
            seg_out.append({
                "i": gi, "start": None, "end": None, "text": "".join(group),
                "sentence_from": first, "sentence_to": len(sent_out),
                "failed": True,
            })
            await asyncio.sleep(2.0)
            continue

        dur = _bytes_duration(audio)
        if not dur:
            dur = max(1.0, len(spoken) / 4.5)
            logger.warning("听读第 %d 段无法测长，按字数兜底 %.1fs", gi + 1, dur)

        # 段内按**实际朗读字数**分摊时长给各句（见模块 docstring 里的精度说明）。
        # 权重取 speakable 后的长度：念的是清掉标记的文本，按原文长度分会让含
        # 表格/标记多的句子分到明显偏多的时间。
        base = sum(_speak_len(s) for s in group) or 1
        t = cursor
        first = len(sent_out)
        for s in group:
            d = dur * (_speak_len(s) / base)
            sent_out.append({"text": s, "start": round(t, 3), "end": round(t + d, 3)})
            t += d
        seg_out.append({
            "i": gi,
            "start": round(cursor, 3),
            "end": round(cursor + dur, 3),
            "text": "".join(group),
            "sentence_from": first,
            "sentence_to": len(sent_out),
        })
        cursor += dur
        parts.append(audio)
        if on_progress is not None:
            try:
                await on_progress(gi + 1, total)
            except Exception as e:  # noqa: BLE001
                # 进度回写失败不该拖垮合成（一讲可能是半小时的活）
                logger.warning("听读进度回调失败（已忽略）%d/%d: %s", gi + 1, total, e)
        if gi % 5 == 0 or gi == total - 1:
            logger.info("听读进度 %d/%d", gi + 1, total)

    if not parts:
        raise TTSError(f"听读合成失败：{total} 段全部失败")

    audio_bytes = b"".join(parts)
    real = _bytes_duration(audio_bytes)
    timeline = {
        "version": TIMELINE_VERSION,
        "duration": round(real or cursor, 3),
        "provider": provider,
        "voice": voice_name,
        "speed": speed,
        "sentences": sent_out,
        "segments": seg_out,
        "failed_segments": failed,
    }
    if failed:
        logger.warning("听读 %d/%d 段失败（索引 %s），这些句子将无高亮",
                       len(failed), total, failed)

    # 覆盖率按「念出来的字数」算：拿原文长度比会把表格/标记算成没念到的字，
    # 每次 prepare 都报一条假的「覆盖不足」警告。
    #
    # 预期时长必须按**汉字/非汉字分估**，不能统一按中文语速 5.2 字/秒：代码页里
    # 九成是非汉字，而 TTS 念代码/英文快得多。实测第14章第2讲（45 段全成功、
    # 227 句零缺失）非汉字占 91%，实测 676s、混合预期 588s（覆盖 115%），
    # 可统一按 5.2 算却得出「预期 1364s、覆盖 53%」——把健康的一讲报成「大半未合成」。
    _expected = sum(_expected_speech_seconds(speakable(s["text"])) for s in sent_out)
    _validate_coverage(
        sum(_speak_len(s["text"]) for s in sent_out),
        int(real) if real else None,
        label="听读",
        expected_sec=_expected / max(speed, 0.5),
    )
    return audio_bytes, timeline


# ---------------------------------------------------------------- 内容寻址缓存

def cache_key(text: str, voice: str, speed: float, provider: str) -> str:
    """同一段文本 + 同一音色/语速/引擎 → 同一个键。

    内容寻址的好处：**平台预置精品课只生成一次，之后 N 个人听都是同一份音频**。
    """
    raw = f"v{TIMELINE_VERSION}|{provider}|{voice}|{_rate_for(speed)}|{normalize_for_hash(text)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _cache_dir() -> Path:
    return Path(settings.podcast_audio_dir) / "listen_cache"


def cache_paths(key: str) -> tuple[Path, Path]:
    d = _cache_dir()
    return d / f"{key}.mp3", d / f"{key}.json"


def load_cached(key: str) -> tuple[bytes, dict] | None:
    """读缓存；文件缺失或损坏都返回 None（损坏时清掉，下次重新生成）。"""
    mp3_path, json_path = cache_paths(key)
    if not (mp3_path.exists() and json_path.exists()):
        return None
    try:
        return mp3_path.read_bytes(), json.loads(json_path.read_text("utf-8"))
    except Exception as e:  # noqa: BLE001
        logger.warning("听读缓存损坏，已清除 %s: %s", key, e)
        for p in (mp3_path, json_path):
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass
        return None


def store_cache(key: str, audio: bytes, timeline: dict) -> None:
    """写缓存。先写 json 再写 mp3，最后才落 mp3 —— load_cached 要求两者都在，
    所以中途崩溃只会留下一份被忽略的 json，不会产生「有时间轴没音频」的半成品。"""
    mp3_path, json_path = cache_paths(key)
    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(timeline, ensure_ascii=False), "utf-8")
    mp3_path.write_bytes(audio)