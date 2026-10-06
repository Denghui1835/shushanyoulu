"""AI 播客 · TTS 封装：把双人对谈文稿合成为单个音频文件。

provider（backend/.env TTS_PROVIDER）：
- edge（默认，免费免 Key）：开源 edge-tts 包（github.com/rany2/edge-tts），
  走微软 Edge 在线神经语音。注意：edge-tts 不支持 SSML（实测会当正文朗读），
  因此这里逐句（turn）用「纯文本 + 对应音色 + 语速/音调」合成后字节拼接，
  保证两位主播音色不同、且绝不读出「主播A：」等标签或乱码。
- volc（火山引擎/豆包 TTS，付费可选）：逐句按说话人调用对应音色后字节拼接。
- azure（Azure 认知服务 TTS，付费可选）：逐句按说话人调用对应音色后字节拼接。
- mock：不联网，生成与文稿长度对应的无声 WAV（纯链路测试/无网时体验 UI 用）。

拼接依赖同源编码一致（edge-tts 输出无 ID3 头、帧同步开头，可直接拼接）；
如需更精细的静音间隔/淡入淡出，可后续引入 ffmpeg/pydub 重新合成。
"""
import asyncio
import base64
import hashlib
import hmac
import logging
import math
import re as _re
import uuid
import wave
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.podcast import parse_turns
from app.models import PodcastScript

logger = logging.getLogger("yuanqi.podcast_tts")

_DEFAULT_TIMEOUT = 120
_SPEAKER_A, _SPEAKER_B = "主播A", "主播B"


class TTSNotConfiguredError(RuntimeError):
    pass


class TTSError(RuntimeError):
    pass


@dataclass
class TTSContext:
    """一次合成该用哪家 TTS、什么音色、什么凭据。

    存在的理由：以前 `_resolve_provider()` 是**无参的全局函数**，读的是
    `settings.tts_provider` —— 等于全服务器只能有一家 TTS。用户自带豆包凭据
    也无处可放。现在把「用哪家 + 凭据」打包成对象按请求传进来，
    不传就回落 settings（完全向后兼容）。

    凭据放对象里而不是读 settings，是为了**不污染全局状态**：
    甲用户的 Key 绝不能出现在乙用户的请求里。
    """
    provider: str                      # edge | volc_mega | volc_standard | azure | mock
    voice_a: str | None = None
    voice_b: str | None = None
    volc_app_id: str | None = None
    volc_access_token: str | None = None
    volc_cluster: str | None = None
    azure_key: str | None = None
    azure_region: str | None = None


async def resolve_tts_context(db: AsyncSession, user_id: str | None) -> TTSContext:
    """查该用户的「语音」档；没配或解不开就回落到 settings 的全局 TTS。

    回落是**有意为之**：语音档没配不等于不能听 —— edge 免费档人人可用，
    这也正是「语音默认 edge」这个产品决策的落点。
    """
    if user_id and user_id != "local_user":
        try:
            from app.core.provider_config import load_options
            from app.core.crypto import decrypt_secret
            from app.models import UserProviderConfig

            row = (await db.execute(
                select(UserProviderConfig).where(
                    UserProviderConfig.user_id == user_id,
                    UserProviderConfig.capability == "tts",
                )
            )).scalars().first()
            if row:
                opts = load_options(row)
                secret = decrypt_secret(row.secret_encrypted,
                                        owner=f"{user_id}/tts") if row.secret_encrypted else {}
                provider = (row.provider or "edge").strip().lower()
                if provider == "volc":
                    provider = "volc_mega"
                if provider == "volc_mega" and not secret.get("access_token"):
                    logger.warning("用户 %s 的语音档凭据缺失/解不开，本次回落全局 TTS", user_id)
                else:
                    return TTSContext(
                        provider=provider,
                        voice_a=opts.get("voice_a") or None,
                        voice_b=opts.get("voice_b") or None,
                        volc_app_id=secret.get("app_id") or None,
                        volc_access_token=secret.get("access_token") or None,
                        volc_cluster=opts.get("cluster") or None,
                        azure_key=secret.get("api_key") or None,
                        azure_region=opts.get("region") or None,
                    )
        except Exception as e:  # noqa: BLE001
            logger.warning("解析用户 %s 的语音档失败（%s），本次回落全局 TTS", user_id, e)

    return TTSContext(provider=(settings.tts_provider or "edge").strip().lower())


def _resolve_provider(ctx: TTSContext | None = None) -> str:
    """确定本次用哪家 provider。传 ctx 用它的，否则读全局 settings。"""
    provider = (ctx.provider if ctx else (settings.tts_provider or "edge")).strip().lower()

    if provider == "edge":
        try:
            import edge_tts  # noqa: F401
        except ImportError:
            raise TTSNotConfiguredError(
                "未安装 edge-tts：请运行 `pip install edge-tts`（免费开源，无需任何 Key）")
    elif provider == "azure":
        key = (ctx.azure_key if ctx else None) or settings.azure_tts_key
        region = (ctx.azure_region if ctx else None) or settings.azure_tts_region
        if not key or not region:
            raise TTSNotConfiguredError(
                "未配置 Azure TTS：请在「个人中心 → AI 服务商 → 语音」填订阅密钥与区域，"
                "或在 backend/.env 填 AZURE_TTS_KEY / AZURE_TTS_REGION")
    elif provider == "mock":
        return provider
    elif provider in ("volc", "volc_mega", "volc_standard"):
        app_id = (ctx.volc_app_id if ctx else None) or settings.volc_app_id
        token = (ctx.volc_access_token if ctx else None) or settings.volc_access_token
        if not app_id or not token:
            raise TTSNotConfiguredError(
                "未配置火山引擎 TTS：请在「个人中心 → AI 服务商 → 语音」填 App ID / Access Token，"
                "或在 backend/.env 填 VOLC_APP_ID / VOLC_ACCESS_TOKEN "
                "（免费方案：用 edge 档，无需任何 Key）")
        provider = "volc_mega" if provider == "volc" else provider  # 默认大模型音色集群
    return provider


def _volc_cluster_for(provider: str, ctx: TTSContext | None = None) -> str:
    """volc_mega → volcano_mega（大模型音色）；volc_standard → volcano_tts（普通音色）。"""
    if ctx and ctx.volc_cluster:
        return ctx.volc_cluster
    if provider == "volc_standard":
        return "volcano_tts"
    return "volcano_mega"


def _voice_for(provider: str, speaker: str, ctx: TTSContext | None = None) -> str:
    if speaker != _SPEAKER_A:
        speaker = _SPEAKER_B
    if provider == "azure":
        if ctx and (ctx.voice_a or ctx.voice_b):
            return (ctx.voice_a if speaker == _SPEAKER_A else ctx.voice_b) or settings.azure_tts_voice_a
        return settings.azure_tts_voice_a if speaker == _SPEAKER_A else settings.azure_tts_voice_b
    # 注意：_resolve_provider 返回的是 volc_mega / volc_standard，**不是** "volc"。
    # 旧代码只判 == "volc"，于是豆包音色永远选不中、静默掉回 edge 音色（已修）。
    if provider in ("volc", "volc_mega", "volc_standard"):
        if ctx and (ctx.voice_a or ctx.voice_b):
            return (ctx.voice_a if speaker == _SPEAKER_A else ctx.voice_b) or settings.volc_tts_voice_a
        return settings.volc_tts_voice_a if speaker == _SPEAKER_A else settings.volc_tts_voice_b
    if ctx and (ctx.voice_a or ctx.voice_b):
        return (ctx.voice_a if speaker == _SPEAKER_A else ctx.voice_b) or settings.edge_tts_voice_a
    return settings.edge_tts_voice_a if speaker == _SPEAKER_A else settings.edge_tts_voice_b


# ---------------------------------------------------------------- edge（免费，逐句纯文本合成）

# 两位主播的语速/音调：让对谈更有情感与区分度（女主播更轻快上扬、男主播沉稳稍低）
_EDGE_TURN_STYLE = {
    "主播A": {"rate": "+10%", "pitch": "+3Hz"},
    "主播B": {"rate": "+6%", "pitch": "-2Hz"},
}
# 句间停顿：不同说话人之间在句尾追加省略号，让换人更自然
_EDGE_TURN_PAUSE = "……"
# 连续请求间隔（秒）：edge-tts 快速连续请求会被微软限流，需给服务喘息
_EDGE_REQUEST_INTERVAL = 0.6
# 单句合成失败重试次数与退避（微软限流 NoAudioReceived 需更长时间恢复）
_EDGE_RETRIES = 6


def merge_speaker_segments(turns: list[dict]) -> list[dict]:
    """合并连续同一说话人的轮次：减少 TTS 调用次数（降低限流风险），
    且同一人连续表达时更连贯（不插入人工停顿）。"""
    merged: list[dict] = []
    for t in turns:
        if merged and merged[-1]["speaker"] == t["speaker"]:
            merged[-1]["text"] += t["text"]
        else:
            merged.append({"speaker": t["speaker"], "text": t["text"]})
    return merged


async def _edge_synthesize(text: str, voice: str, rate: str = "+0%", pitch: str = "+0Hz") -> bytes:
    """edge-tts 合成一段（纯文本，不含任何 SSML/标签），返回 mp3 字节。

    带失败重试：微软服务偶发限流（NoAudioReceived），重试退避后可恢复。
    合成后校验：若输出音频时长显著短于预期（沉默截断/流中断），同样触发重试。
    """
    import edge_tts

    _MIN_DURATION_RATIO = 0.70
    # 允许的音频时长下限比率：实测 < 预期 * 0.7 则认为流被截断

    last_err: Exception | None = None
    for attempt in range(_EDGE_RETRIES):
        try:
            communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
            audio = bytearray()
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio":
                    audio.extend(chunk["data"])
            if not audio:
                raise TTSError("edge-tts 返回为空")

            # 校验：估算音频应该有多长，如果太短说明 edge-tts 静默截断了
            expected_sec = _expected_speech_seconds(text)
            # 用 MP3 帧数粗估时长（更快，不依赖 mutagen）
            mp3_bytes = bytes(audio)
            actual_sec = _mp3_bytes_duration_estimate(mp3_bytes)
            if actual_sec is not None and expected_sec > 1.5 and actual_sec < expected_sec * _MIN_DURATION_RATIO:
                # 偏短有两种成因，必须分开对待：
                # ① 真截断（偶发）→ 重试一次通常就好；
                # ② 内容本身就念得快（代码块/英文）→ 重试多少次结果都一样，**采用它**。
                # ②曾经被永久丢弃：实测一整章的 Python 代码块全部静音，且因为判定是
                # 确定性的，每次重生成都失败。静音远比「略短的音频」糟糕。
                if attempt == 0:
                    last_err = TTSError(
                        f"edge-tts 输出异常短：预期 {expected_sec:.1f}s, 实际 {actual_sec:.1f}s "
                        f"(文本 {len(text)} 字)，可能被服务端截断")
                    await asyncio.sleep(1.5)
                    continue
                logger.warning("edge-tts 输出偏短但已重试过，采用（宁可短也别静音）："
                               "预期 %.1fs 实测 %.1fs（文本 %d 字）",
                               expected_sec, actual_sec, len(text))
                return mp3_bytes

            return mp3_bytes
        except TTSError:
            raise  # 不吞我们自己的错误（包括截断检测）
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < _EDGE_RETRIES - 1:
                await asyncio.sleep(2.0 + attempt * 2.5)
    raise TTSError(f"edge-tts 合成失败：{last_err}")


# 中文散文的朗读语速（字/秒）。**只对汉字成立**——拿它去量英文和代码会恒判
# 「截断」，见 _expected_speech_seconds。
_CJK_CHARS_PER_SEC = 5.0
# 非汉字字符（英文、数字、符号、源码）的等效语速。TTS 念这些明显更快，
# 所以这个数取得偏大、宁可低估时长：防截断闸门「漏判」只是偶尔放过一段略短的
# 音频，而「误判」会让整类内容永久静音——两种都踩过（表格标记、代码块）。
_OTHER_CHARS_PER_SEC = 14.0


def _expected_speech_seconds(text: str) -> float:
    """按内容估算「这段文本念出来大约多久」。

    原先一律按 `len(text) / 4.5` 估。4.5 字/秒是**中文散文**的经验值，可 TTS 念
    代码和英文快得多（符号常常一带而过），于是含代码块的段落实测时长只有预估的
    一半，被防截断闸门判成「服务端截断」而丢掉。

    实测依据（第14章一讲，42 段里 13 段失败）：失败句平均 ASCII 占比 0.84，
    正常句 0.18，失败样例是 `import matplotlib.pyplot as plt` 这类源码。
    所以汉字与非汉字分开算。
    """
    cjk = 0
    for ch in text:
        if "一" <= ch <= "鿿":
            cjk += 1
    other = max(0, len(text) - cjk)
    return cjk / _CJK_CHARS_PER_SEC + other / _OTHER_CHARS_PER_SEC


def _mp3_bytes_duration_estimate(data: bytes) -> float | None:
    """从 MP3 字节估算时长（秒）。用 mutagen 从内存解析，比手动数帧准。"""
    try:
        from mutagen.mp3 import MP3
        from io import BytesIO as _BytesIO
        return MP3(_BytesIO(data)).info.length
    except Exception:
        return None


# ---------------------------------------------------------------- volc / azure / mock（逐句）

async def _synthesize(provider: str, text: str, voice: str,
                      ctx: TTSContext | None = None) -> bytes:
    if provider == "azure":
        return await _azure_synthesize(text, voice, ctx=ctx)
    if provider == "mock":
        return await _mock_synthesize(text)
    cluster = _volc_cluster_for(provider, ctx) if provider in ("volc_mega", "volc_standard") else None
    return await _volc_synthesize(text, voice, cluster=cluster, ctx=ctx)


async def _volc_synthesize(text: str, voice: str, cluster: str | None = None,
                           ctx: TTSContext | None = None) -> bytes:
    """火山引擎/豆包语音合成 HTTP 接口（v1 tts）。返回 mp3 字节。

    鉴权：Authorization = "Bearer; <APPID>; <TOKEN>"，
    TOKEN = base64(HMAC-SHA256(access_token, "volc.megatts.default"))。
    cluster 默认 settings.volc_tts_cluster；volc_mega→volcano_mega、volc_standard→volcano_tts。
    凭据优先取 ctx（用户自带），其次 settings（服务器全局）。
    """
    app_id = (ctx.volc_app_id if ctx else None) or settings.volc_app_id
    access_token = (ctx.volc_access_token if ctx else None) or settings.volc_access_token
    url = "https://openspeech.bytedance.com/api/v1/tts"
    resource_id = "volc.megatts.default"
    digest = hmac.new(
        access_token.encode("utf-8"),
        resource_id.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    token = base64.b64encode(digest).decode()
    body = {
        "app": {
            "appid": app_id,
            "token": access_token,
            "cluster": cluster or settings.volc_tts_cluster,
        },
        "user": {"uid": "yq_podcast"},
        "audio": {
            "voice_type": voice,
            "encoding": "mp3",
            "speed_ratio": 1.0,
            "volume_ratio": 1.0,
            "pitch_ratio": 1.0,
        },
        "request": {"reqid": str(uuid.uuid4()), "text": text, "operation": "query"},
    }
    headers = {"Authorization": f"Bearer; {app_id}; {token}",
               "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
        resp = await client.post(url, json=body, headers=headers)
        data = resp.json()
    code = data.get("code")
    if code != 3000:
        raise TTSError(f"火山 TTS 返回错误: code={code} {data.get('message', '')[:200]}")
    raw = data.get("data") or data.get("audio_data")
    if not raw:
        raise TTSError("火山 TTS 返回为空")
    return base64.b64decode(raw)


async def _azure_synthesize(text: str, voice: str,
                            ctx: TTSContext | None = None) -> bytes:
    """Azure 认知服务 TTS（REST）。返回 mp3 字节。"""
    key = (ctx.azure_key if ctx else None) or settings.azure_tts_key
    region = (ctx.azure_region if ctx else None) or settings.azure_tts_region
    url = (f"https://{region}.tts.speech.microsoft.com"
           "/cognitiveservices/v1")
    import xml.sax.saxutils as sax
    ssml = (
        "<speak version='1.0' xml:lang='zh-CN'>"
        f"<voice name='{voice}'><prosody rate='+0%'>{sax.escape(text)}</prosody></voice>"
        "</speak>"
    )
    headers = {
        "Ocp-Apim-Subscription-Key": key,
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": "audio-24khz-96kbitrate-mono-mp3",
    }
    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
        resp = await client.post(url, headers=headers, content=ssml.encode("utf-8"))
    if resp.status_code != 200:
        raise TTSError(f"Azure TTS 错误: {resp.status_code} {resp.text[:200]}")
    return resp.content


def _mock_synthesize(text: str) -> bytes:
    """Mock：按字数生成一段无声 WAV（约 4.5 字/秒，与正常语速接近），可被浏览器播放。"""
    rate = 24000
    duration = max(1.0, len(text) / 4.5)
    frames = int(rate * duration)
    buf = BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * frames)
    return buf.getvalue()


# ---------------------------------------------------------------- 整篇合成

async def script_to_audio(db: AsyncSession, script: PodcastScript,
                          tts_ctx: TTSContext | None = None) -> PodcastScript:
    """把文稿合成音频存盘并回填 audio_path。

    统一走「逐句合成 + 字节拼接」：每句用对应说话人的音色（edge 再加语速/音调），
    保证两位主播音色不同、句间带自然停顿，绝不读出标签/乱码。
    provider 未配置/未安装抛 TTSNotConfiguredError；单段合成失败记录告警后继续（不因一段失败丢全文）。
    全部段均失败才抛 TTSError。
    """
    turns = parse_turns(script.content)
    if not turns:
        raise TTSError("文稿不是有效的双人对谈格式，请重新生成")

    provider = _resolve_provider(tts_ctx)
    out_dir = Path(settings.podcast_audio_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # 文件名带 provider：文稿是**按文档共享**的，但 provider 现在是**按用户**的。
    # 不带 provider 的话，甲用 edge、乙用豆包，乙生成一次就会把甲那条音频文件覆盖掉，
    # 而甲的 script.audio_path 还指着这个路径 —— 会放出别人音色的音频。
    out_path = out_dir / f"{script.document_id[:8]}_u{script.unit_index}_{provider}.mp3"

    # 合并连续同一说话人，减少调用次数（降低限流风险）
    segments = merge_speaker_segments(turns)
    parts: list[bytes] = []
    total = len(segments)
    failed_segments: list[int] = []
    skipped_empty: list[int] = []
    spoken_chars = 0   # 累计实际送入合成的字符数（含段间停顿）

    for i, seg in enumerate(segments):
        text = (seg.get("text") or "").strip()
        if not text:
            skipped_empty.append(i)
            continue
        # 不同说话人之间追加省略号停顿，让换人更自然（segments 已合并，相邻必为不同人）
        if i < total - 1:
            text = text.rstrip("。！？!?") + "。" + _EDGE_TURN_PAUSE
        spoken_chars += len(text)
        voice = _voice_for(provider, seg["speaker"], tts_ctx)

        try:
            if provider == "edge":
                style = _EDGE_TURN_STYLE.get(seg["speaker"], {})
                part = await _edge_synthesize(text, voice,
                                              style.get("rate", "+0%"), style.get("pitch", "+0Hz"))
                if i < total - 1:
                    await asyncio.sleep(_EDGE_REQUEST_INTERVAL)  # 给 edge 服务喘息，防限流
            else:
                part = await _synthesize(provider, text, voice, ctx=tts_ctx)
        except Exception as e:
            logger.error("TTS 第 %d/%d 段合成失败 (%s): %s", i + 1, total, seg["speaker"], e)
            failed_segments.append(i)
            # 失败后稍长等待，给服务恢复时间
            await asyncio.sleep(2.0)
            continue

        if part:
            parts.append(part)
            if i % 5 == 0 or i == total - 1:
                logger.info("TTS 进度 %d/%d (%s)", i + 1, total, seg["speaker"])
        else:
            logger.warning("TTS 第 %d/%d 段返回空字节 (%s)，跳过", i + 1, total, seg["speaker"])
            failed_segments.append(i)

    # 汇总缺失情况
    if skipped_empty:
        logger.warning("TTS 跳过 %d 个空文本段（索引 %s），原文稿可能有异常行",
                       len(skipped_empty), skipped_empty[:10])
    if failed_segments:
        logger.warning("TTS %d/%d 段合成失败（索引 %s），音频可能缺失部分内容",
                       len(failed_segments), total, failed_segments)

    if not parts:
        raise TTSError(f"TTS 未产出任何音频：{total} 段中 {len(failed_segments)} 段失败")

    out_path.write_bytes(b"".join(parts))
    real_sec = _mp3_seconds(str(out_path))
    logger.info("播客音频已生成: %s (%d 段, %d KB, 实测 %s 秒)",
                out_path.name, total, out_path.stat().st_size // 1024,
                real_sec if real_sec else "未知")

    # 覆盖校验：对比送入合成的字符数 vs 实测音频时长
    _validate_coverage(spoken_chars, real_sec,
                       chars_per_sec=5.2,
                       label=f"播客 {script.document_id[:8]}_u{script.unit_index}")

    script.audio_path = str(out_path)
    script.audio_seconds = real_sec
    script.status = "done"
    await db.commit()
    await db.refresh(script)
    return script


def estimate_audio_seconds(content: str) -> int:
    """按口播字数估算播客时长（秒），供前端展示（无实测时长时兜底）。

    只计说话人实际文本（不含「主播A：」标签与空行）；
    实际口播速度约 5.2 字/秒（edge 语速 +6%~+10%）。
    """
    spoken = sum(len(t.get("text") or "") for t in parse_turns(content or ""))
    return max(1, math.ceil(spoken / 5.2))


def _mp3_seconds(path: str) -> int | None:
    """读 mp3 真实时长（秒）；解析失败返回 None。"""
    try:
        from mutagen.mp3 import MP3
        return int(MP3(path).info.length)
    except Exception:
        return None


# ---------------------------------------------------------------- 通用 TTS（/api/tts）

# 自然朗读：按标点分句后分组，让 edge-tts 逐段合成（音调微妙起伏 + 句间停顿），
# 避免一整段扔进去 → 语调平直像机器人。对标豆包/真人朗读的呼吸感。

_SENTENCE_SPLIT_RE = _re.compile(r'(?<=[。！？；\n])')
_SEGMENT_MAX_CHARS = 350   # 每段最多字符数（≈ 1 分钟朗读），超长拆分保证语调鲜活
# 音调微妙起伏（循环使用，模拟真人说话的情绪微变化，不重复单调）
_READ_PITCH_CYCLE = ("+2Hz", "+3Hz", "+1Hz", "+2Hz", "+0Hz")
_READ_PAUSE = "……"        # 段间自然停顿（轻声，不被当作正文朗读）


# ---------------------------------------------------------------- 覆盖校验

def _validate_coverage(input_chars: int, audio_seconds: int | None,
                       chars_per_sec: float = 5.2, label: str = "",
                       expected_sec: float | None = None) -> None:
    """校验合成音频是否覆盖了全部输入文本。

    audio_seconds 为 None（无法读取时长）或 input_chars ≤ 0 时跳过。
    覆盖率 < 90% 时打印 WARNING，< 60% 时打印 ERROR。

    预期时长默认按 `input_chars / chars_per_sec` 折算。**这个折算对含代码/英文的页
    是错的**：统一按中文语速（5.2 字/秒）估，而 TTS 念代码和英文快得多，于是
    一篇 91% 是非汉字的讲实测 676s，却被算出「预期 1364s、覆盖 53%」——健康的一讲
    被报成「大半内容未被合成」。调用方若知道更准的预期（如汉字/非汉字分估），传
    `expected_sec` 覆盖它（见 core/listen_tts.py 的调用）。
    """
    if audio_seconds is None or input_chars <= 0:
        return
    if expected_sec is None:
        expected_sec = input_chars / chars_per_sec
    if expected_sec <= 0:
        return
    coverage = audio_seconds / expected_sec
    tag = f" [{label}]" if label else ""
    if coverage < 0.60:
        logger.error(
            "TTS 严重缺失%s: 输入 %d 字 → 预期 %.1f秒, 实测 %d秒, 覆盖率 %.0f%% — 大半内容未被合成！",
            tag, input_chars, expected_sec, audio_seconds, coverage * 100)
    elif coverage < 0.90:
        logger.warning(
            "TTS 覆盖不足%s: 输入 %d 字 → 预期 %.1f秒, 实测 %d秒, 覆盖率 %.0f%%",
            tag, input_chars, expected_sec, audio_seconds, coverage * 100)


def _split_text_segments(text: str) -> list[str]:
    """按中文标点断句后分组，保证每段在自然停顿处断开（不会在词中断开）。"""
    parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(text) if p.strip()]
    if not parts:
        return [text]
    segments: list[str] = []
    cur = ""
    for p in parts:
        if len(cur) + len(p) > _SEGMENT_MAX_CHARS and cur:
            segments.append(cur)
            cur = p
        else:
            cur += p
    if cur.strip():
        segments.append(cur.strip())
    return segments if segments else [text]


async def synthesize_text(text: str, voice: str | None = None,
                          speed: float = 1.0, provider: str | None = None,
                          tts_ctx: TTSContext | None = None) -> bytes:
    """通用文本合成（供 /api/tts/synthesize）。按句分组合成，比整段朗读更自然。

    edge 免费方案：分段→ 每段用微妙音调变化合成 → 段间加自然停顿 → MP3 拼接。
    让朗读有「呼吸感」，不像机器人念经。
    单段失败记录告警后继续，全部失败才抛错；合成完后校验覆盖率。

    `provider` 显式给了就压过 ctx（测试页会显式指定）；否则用 ctx 或全局。
    """
    p = (provider or (tts_ctx.provider if tts_ctx else None)
         or settings.tts_provider).strip().lower()
    if p == "edge":
        rate = f"+{int((speed - 1) * 100)}%" if speed >= 1 else f"{int((speed - 1) * 100)}%"
        voice_name = voice or (tts_ctx.voice_a if tts_ctx else None) or settings.edge_tts_voice_a

        segments = _split_text_segments(text)
        # 单段短文本：直接合成（也加音调 + 校验）
        if len(segments) <= 1:
            return await _edge_synthesize(text, voice_name, rate=rate, pitch="+2Hz")

        # 长文本：逐段合成，每段微调 pitch 模拟真人情绪起伏
        parts: list[bytes] = []
        total = len(segments)
        failed: list[int] = []
        spoken_chars = 0

        for i, seg in enumerate(segments):
            # 段间追加自然停顿（轻声省略号），让听众有"换气"感
            if i < total - 1:
                seg = seg.rstrip("。！？!?") + "。" + _READ_PAUSE
            spoken_chars += len(seg)
            pitch = _READ_PITCH_CYCLE[i % len(_READ_PITCH_CYCLE)]

            try:
                part = await _edge_synthesize(seg, voice_name, rate=rate, pitch=pitch)
            except Exception as e:
                logger.error("TTS 朗读第 %d/%d 段失败: %s", i + 1, total, e)
                failed.append(i)
                await asyncio.sleep(2.0)
                continue

            if part:
                parts.append(part)
            else:
                failed.append(i)
            if i < total - 1:
                await asyncio.sleep(_EDGE_REQUEST_INTERVAL)

        if failed:
            logger.warning("TTS 朗读 %d/%d 段失败（索引 %s），音频可能不完整",
                           len(failed), total, failed)
        if not parts:
            raise TTSError(f"edge-tts 未返回任何音频：{total} 段全部失败")

        result = b"".join(parts)
        # 覆盖校验：用 bytes 长度估算时长（不阻塞 async）
        est_sec = _mp3_bytes_duration_estimate(result)
        if est_sec is not None:
            _validate_coverage(spoken_chars, int(est_sec), chars_per_sec=5.2, label="朗读")
        return result

    if p in ("volc", "volc_mega", "volc_standard"):
        app_id = (tts_ctx.volc_app_id if tts_ctx else None) or settings.volc_app_id
        token = (tts_ctx.volc_access_token if tts_ctx else None) or settings.volc_access_token
        if not app_id or not token:
            raise TTSNotConfiguredError(
                "未配置火山引擎/豆包 TTS：请在「个人中心 → AI 服务商 → 语音」填 "
                "App ID / Access Token，或在 backend/.env 填 VOLC_APP_ID / VOLC_ACCESS_TOKEN")
        v = voice or (tts_ctx.voice_a if tts_ctx else None) or settings.volc_tts_voice_a
        cluster = _volc_cluster_for("volc_mega" if p == "volc" else p, tts_ctx)
        return await _volc_synthesize(text, v, cluster=cluster, ctx=tts_ctx)
    if p == "azure":
        return await _azure_synthesize(
            text, voice or (tts_ctx.voice_a if tts_ctx else None) or settings.azure_tts_voice_a,
            ctx=tts_ctx)
    if p == "mock":
        return _mock_synthesize(text)
    raise TTSError(f"未知 TTS provider: {p}")


def list_voices() -> list[dict]:
    """列出所有已配置的可用音色（edge + 豆包 + azure）。"""
    return [
        {"provider": "edge", "id": "zh-CN-XiaoxiaoNeural", "name": "晓晓·女声（免费）"},
        {"provider": "edge", "id": "zh-CN-YunxiNeural", "name": "云希·男声（免费）"},
        {"provider": "edge", "id": "zh-CN-YunyangNeural", "name": "云扬·男声（免费）"},
        {"provider": "edge", "id": "zh-CN-liaoning-XiaobeiNeural", "name": "晓北·东北女声（免费）"},
        {"provider": "edge", "id": "zh-CN-shaanxi-XiaoniNeural", "name": "晓妮·陕西女声（免费）"},
        {"provider": "volc_mega", "id": "BV001_streaming", "name": "灿灿·女声（豆包）"},
        {"provider": "volc_mega", "id": "BV700_streaming", "name": "辉晓·男声（豆包）"},
        {"provider": "volc_mega", "id": "BV002_streaming", "name": "通用男声（豆包）"},
        {"provider": "volc_standard", "id": "BV700", "name": "辉晓·男声（豆包普通）"},
        {"provider": "azure", "id": "zh-CN-XiaoxiaoNeural", "name": "晓晓·女声（Azure）"},
        {"provider": "azure", "id": "zh-CN-YunxiNeural", "name": "云希·男声（Azure）"},
    ]
