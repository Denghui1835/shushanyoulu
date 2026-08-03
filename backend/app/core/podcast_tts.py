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
import uuid
import wave
from io import BytesIO
from pathlib import Path

import httpx
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


def _resolve_provider() -> str:
    provider = (settings.tts_provider or "edge").strip().lower()
    if provider == "edge":
        try:
            import edge_tts  # noqa: F401
        except ImportError:
            raise TTSNotConfiguredError(
                "未安装 edge-tts：请运行 `pip install edge-tts`（免费开源，无需任何 Key）")
    elif provider == "azure":
        if not settings.azure_tts_key or not settings.azure_tts_region:
            raise TTSNotConfiguredError(
                "未配置 Azure TTS：请在 backend/.env 填 AZURE_TTS_KEY / AZURE_TTS_REGION")
    elif provider == "mock":
        return provider
    elif provider in ("volc", "volc_mega", "volc_standard"):
        if not settings.volc_app_id or not settings.volc_access_token:
            raise TTSNotConfiguredError(
                "未配置火山引擎 TTS：请在 backend/.env 填 VOLC_APP_ID / VOLC_ACCESS_TOKEN "
                "（免费方案：TTS_PROVIDER=edge 无需任何 Key）")
        provider = "volc_mega" if provider == "volc" else provider  # 默认大模型音色集群
    return provider


def _volc_cluster_for(provider: str) -> str:
    """volc_mega → volcano_mega（大模型音色）；volc_standard → volcano_tts（普通音色）。"""
    if provider == "volc_standard":
        return "volcano_tts"
    return "volcano_mega"


def _voice_for(provider: str, speaker: str) -> str:
    if speaker != _SPEAKER_A:
        speaker = _SPEAKER_B
    if provider == "azure":
        return settings.azure_tts_voice_a if speaker == _SPEAKER_A else settings.azure_tts_voice_b
    if provider == "volc":
        return settings.volc_tts_voice_a if speaker == _SPEAKER_A else settings.volc_tts_voice_b
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
_EDGE_REQUEST_INTERVAL = 0.25
# 单句合成失败重试次数与退避
_EDGE_RETRIES = 4


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
    """
    import edge_tts

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
            return bytes(audio)
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < _EDGE_RETRIES - 1:
                await asyncio.sleep(1.5 + attempt * 1.5)
    raise TTSError(f"edge-tts 合成失败：{last_err}")


# ---------------------------------------------------------------- volc / azure / mock（逐句）

async def _synthesize(provider: str, text: str, voice: str) -> bytes:
    if provider == "azure":
        return await _azure_synthesize(text, voice)
    if provider == "mock":
        return _mock_synthesize(text)
    cluster = _volc_cluster_for(provider) if provider in ("volc_mega", "volc_standard") else None
    return await _volc_synthesize(text, voice, cluster=cluster)


async def _volc_synthesize(text: str, voice: str, cluster: str | None = None) -> bytes:
    """火山引擎/豆包语音合成 HTTP 接口（v1 tts）。返回 mp3 字节。

    鉴权：Authorization = "Bearer; <APPID>; <TOKEN>"，
    TOKEN = base64(HMAC-SHA256(access_token, "volc.megatts.default"))。
    cluster 默认 settings.volc_tts_cluster；volc_mega→volcano_mega、volc_standard→volcano_tts。
    """
    url = "https://openspeech.bytedance.com/api/v1/tts"
    resource_id = "volc.megatts.default"
    digest = hmac.new(
        settings.volc_access_token.encode("utf-8"),
        resource_id.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    token = base64.b64encode(digest).decode()
    body = {
        "app": {
            "appid": settings.volc_app_id,
            "token": settings.volc_access_token,
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
    headers = {"Authorization": f"Bearer; {settings.volc_app_id}; {token}",
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


async def _azure_synthesize(text: str, voice: str) -> bytes:
    """Azure 认知服务 TTS（REST）。返回 mp3 字节。"""
    url = (f"https://{settings.azure_tts_region}.tts.speech.microsoft.com"
           "/cognitiveservices/v1")
    import xml.sax.saxutils as sax
    ssml = (
        "<speak version='1.0' xml:lang='zh-CN'>"
        f"<voice name='{voice}'><prosody rate='+0%'>{sax.escape(text)}</prosody></voice>"
        "</speak>"
    )
    headers = {
        "Ocp-Apim-Subscription-Key": settings.azure_tts_key,
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

async def script_to_audio(db: AsyncSession, script: PodcastScript) -> PodcastScript:
    """把文稿合成音频存盘并回填 audio_path。

    统一走「逐句合成 + 字节拼接」：每句用对应说话人的音色（edge 再加语速/音调），
    保证两位主播音色不同、句间带自然停顿，绝不读出标签/乱码。
    provider 未配置/未安装抛 TTSNotConfiguredError；单句合成失败抛 TTSError（由 API 转 500）。
    """
    turns = parse_turns(script.content)
    if not turns:
        raise TTSError("文稿不是有效的双人对谈格式，请重新生成")

    provider = _resolve_provider()
    out_dir = Path(settings.podcast_audio_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{script.document_id[:8]}_u{script.unit_index}.mp3"

    # 合并连续同一说话人，减少调用次数（降低限流风险）
    segments = merge_speaker_segments(turns)
    parts: list[bytes] = []
    total = len(segments)
    for i, seg in enumerate(segments):
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        # 不同说话人之间追加省略号停顿，让换人更自然（segments 已合并，相邻必为不同人）
        if i < total - 1:
            text = text.rstrip("。！？!?") + "。" + _EDGE_TURN_PAUSE
        voice = _voice_for(provider, seg["speaker"])
        if provider == "edge":
            style = _EDGE_TURN_STYLE.get(seg["speaker"], {})
            part = await _edge_synthesize(text, voice,
                                          style.get("rate", "+0%"), style.get("pitch", "+0Hz"))
            if i < total - 1:
                await asyncio.sleep(_EDGE_REQUEST_INTERVAL)  # 给 edge 服务喘息，防限流
        else:
            part = await _synthesize(provider, text, voice)
        if not part:
            logger.warning("TTS 第 %d 段返回空，跳过", i)
            continue
        parts.append(part)
        if i % 5 == 0 or i == total - 1:
            logger.info("TTS 进度 %d/%d (%s)", i + 1, total, seg["speaker"])

    if not parts:
        raise TTSError("TTS 未产出任何音频")
    out_path.write_bytes(b"".join(parts))
    real_sec = _mp3_seconds(str(out_path))
    logger.info("播客音频已生成: %s (%d 段, %d KB, 实测 %s 秒)",
                out_path.name, total, out_path.stat().st_size // 1024,
                real_sec if real_sec else "未知")

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

async def synthesize_text(text: str, voice: str | None = None,
                          speed: float = 1.0, provider: str | None = None) -> bytes:
    """通用单段文本合成（供 /api/tts/synthesize 使用）。返回音频字节。"""
    p = (provider or settings.tts_provider).strip().lower()
    if p == "edge":
        rate = f"+{int((speed - 1) * 100)}%" if speed >= 1 else f"{int((speed - 1) * 100)}%"
        return await _edge_synthesize(text, voice or settings.edge_tts_voice_a, rate=rate)
    if p in ("volc", "volc_mega", "volc_standard"):
        if not settings.volc_app_id or not settings.volc_access_token:
            raise TTSNotConfiguredError(
                "未配置火山引擎/豆包 TTS：请在 backend/.env 填 VOLC_APP_ID / VOLC_ACCESS_TOKEN")
        v = voice or settings.volc_tts_voice_a
        cluster = _volc_cluster_for("volc_mega" if p == "volc" else p)
        return await _volc_synthesize(text, v, cluster=cluster)
    if p == "azure":
        return await _azure_synthesize(text, voice or settings.azure_tts_voice_a)
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
