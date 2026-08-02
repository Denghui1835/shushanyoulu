"""AI 播客 · TTS 封装：把双人对谈文稿合成为单个音频文件。

provider（backend/.env TTS_PROVIDER）：
- edge（默认，免费免 Key）：开源 edge-tts 包（github.com/rany2/edge-tts），
  走微软 Edge 在线神经语音，音质与 Azure 同源、情感自然；用双音色 SSML 单次合成，
  两位主播交替发声、句间带自然停顿，接近豆包 AI 播客的对谈感。
- volc（火山引擎/豆包 TTS，付费可选）：逐句按说话人调用对应音色后字节拼接。
- azure（Azure 认知服务 TTS，付费可选）：逐句按说话人调用对应音色后字节拼接。
- mock：不联网，生成与文稿长度对应的无声 WAV（纯链路测试/无网时体验 UI 用）。

拼接依赖同源编码一致（浏览器一般可顺序播放）；如需更精细的静音间隔/淡入淡出，
可后续引入 ffmpeg/pydub 重新合成。
"""
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
    else:
        if not settings.volc_app_id or not settings.volc_access_token:
            raise TTSNotConfiguredError(
                "未配置火山引擎 TTS：请在 backend/.env 填 VOLC_APP_ID / VOLC_ACCESS_TOKEN "
                "（免费方案：TTS_PROVIDER=edge 无需任何 Key）")
        provider = "volc"
    return provider


def _voice_for(provider: str, speaker: str) -> str:
    if speaker != _SPEAKER_A:
        speaker = _SPEAKER_B
    if provider == "azure":
        return settings.azure_tts_voice_a if speaker == _SPEAKER_A else settings.azure_tts_voice_b
    if provider == "volc":
        return settings.volc_tts_voice_a if speaker == _SPEAKER_A else settings.volc_tts_voice_b
    return settings.edge_tts_voice_a if speaker == _SPEAKER_A else settings.edge_tts_voice_b


# ---------------------------------------------------------------- edge（免费，SSML 双音色单次合成）

def _edge_ssml(turns: list[dict]) -> str:
    """把说话轮次拼成双音色 SSML：两位主播交替、句间带停顿，一次请求完成整期对谈。"""
    import xml.sax.saxutils as sax
    parts = ["<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='zh-CN'>"]
    for i, t in enumerate(turns):
        if i > 0:
            parts.append("<break time='220ms'/>")
        voice = _voice_for("edge", t["speaker"])
        parts.append(f"<voice name='{voice}'>{sax.escape(t['text'])}</voice>")
    parts.append("</speak>")
    return "".join(parts)


async def _edge_synthesize(ssml: str) -> bytes:
    import edge_tts

    communicate = edge_tts.Communicate(ssml, voice=settings.edge_tts_voice_a)  # SSML 内已指定音色
    audio = bytearray()
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio":
            audio.extend(chunk["data"])
    if not audio:
        raise TTSError("edge-tts 返回为空")
    return bytes(audio)


# ---------------------------------------------------------------- volc / azure / mock（逐句）

async def _synthesize(provider: str, text: str, voice: str) -> bytes:
    if provider == "azure":
        return await _azure_synthesize(text, voice)
    if provider == "mock":
        return _mock_synthesize(text)
    return await _volc_synthesize(text, voice)


async def _volc_synthesize(text: str, voice: str) -> bytes:
    """火山引擎/豆包语音合成 HTTP 接口（v1 tts）。返回 mp3 字节。

    鉴权：Authorization = "Bearer; <APPID>; <TOKEN>"，
    TOKEN = base64(HMAC-SHA256(access_token, "volc.megatts.default"))。
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
            "cluster": settings.volc_tts_cluster,
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

    edge：SSML 双音色单次合成（对话自然、无拼接爆音）；
    volc/azure/mock：逐句按说话人调用对应音色后字节拼接。
    provider 未配置/未安装抛 TTSNotConfiguredError；单句合成失败抛 TTSError（由 API 转 500）。
    """
    turns = parse_turns(script.content)
    if not turns:
        raise TTSError("文稿不是有效的双人对谈格式，请重新生成")

    provider = _resolve_provider()
    out_dir = Path(settings.podcast_audio_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{script.document_id[:8]}_u{script.unit_index}.mp3"

    if provider == "edge":
        # 一次请求合成整期对谈（双音色 + 句间停顿）
        ssml = _edge_ssml(turns)
        audio = await _edge_synthesize(ssml)
        logger.info("edge-tts 合成整期播客: %s (%d 轮, %d KB)",
                    out_path.name, len(turns), len(audio) // 1024)
        out_path.write_bytes(audio)
    else:
        parts: list[bytes] = []
        for i, turn in enumerate(turns):
            if not turn["text"]:
                continue
            voice = _voice_for(provider, turn["speaker"])
            part = await _synthesize(provider, turn["text"], voice)
            if not part:
                logger.warning("TTS 第 %d 轮返回空，跳过", i)
                continue
            parts.append(part)
            if i % 5 == 0 or i == len(turns) - 1:
                logger.info("TTS 进度 %d/%d (%s)", i + 1, len(turns), turn["speaker"])
        if not parts:
            raise TTSError("TTS 未产出任何音频")
        out_path.write_bytes(b"".join(parts))
        logger.info("播客音频已生成: %s (%d 轮, %d KB)", out_path.name, len(turns), out_path.stat().st_size // 1024)

    script.audio_path = str(out_path)
    script.status = "done"
    await db.commit()
    await db.refresh(script)
    return script


def estimate_audio_seconds(content: str) -> int:
    """按文稿字数估算播客时长（秒），供前端展示。"""
    return max(1, math.ceil(len(content or "") / 4.5))
