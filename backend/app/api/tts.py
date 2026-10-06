"""通用 TTS API：任意文本转语音（豆包/edge/azure），供语音助手/听书/闪卡朗读等使用。

与播客 TTS（script_to_audio）复用同一套 provider 抽象；豆包为可选增强，edge 免费默认。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from app.core.auth import get_optional_user
from app.core.podcast_tts import (
    synthesize_text, list_voices, resolve_tts_context,
    TTSNotConfiguredError, TTSError,
)
from app.database import get_db
from app.models import User
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("yuanqi.api.tts")
router = APIRouter(prefix="/api/tts", tags=["tts"])


@router.get("/voices")
async def voices():
    """列出可用音色（含豆包 + edge + azure）。"""
    return {"count": len(list_voices()), "voices": list_voices()}


class TTSIn(BaseModel):
    text: str
    voice: str = ""
    speed: float = 1.0      # 0.5-2.0
    provider: str = ""      # 空=用系统默认（edge）


@router.post("/synthesize")
async def synthesize(data: TTSIn, db: AsyncSession = Depends(get_db),
                     user: User | None = Depends(get_optional_user)):
    """合成一段语音，返回音频（mp3/wav）。

    未显式指定 provider 时用**当前用户自己的语音档**（没配则回落全局 edge 免费档）。
    """
    text = (data.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="文本不能为空")
    if len(text) > 2000:
        raise HTTPException(status_code=400, detail="文本过长（≤2000 字）")
    speed = max(0.5, min(2.0, data.speed or 1.0))
    try:
        tts_ctx = await resolve_tts_context(db, user.id if user else None)
        audio = await synthesize_text(text, voice=data.voice or None,
                                      speed=speed, provider=data.provider or None,
                                      tts_ctx=tts_ctx)
    except TTSNotConfiguredError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except TTSError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.exception("TTS 合成失败")
        raise HTTPException(status_code=500, detail=f"合成失败：{str(e)[:200]}")
    media_type = "audio/wav" if _is_wav(audio) else "audio/mpeg"
    return Response(content=audio, media_type=media_type)


def _is_wav(audio: bytes) -> bool:
    return audio[:4] == b"RIFF" and audio[8:12] == b"WAVE"
