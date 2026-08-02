"""AI 播客 API — 文稿生成/查询、音频生成/获取.

对标豆包 AI 播客：每个阅读单元（章节/页）独立成一条播客。
流程：生成文稿（可查看/重新生成）→ 生成音频 → 试听/下载。
"""
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.podcast import generate_podcast_script
from app.core.podcast_tts import (
    TTSNotConfiguredError, TTSError, estimate_audio_seconds, script_to_audio,
)
from app.models import Document, PodcastScript

logger = logging.getLogger("yuanqi.api.podcast")
router = APIRouter(prefix="/api/podcast", tags=["podcast"])


async def _get_doc(db: AsyncSession, document_id: str) -> Document:
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    return doc


async def _get_script(db: AsyncSession, document_id: str, unit_index: int) -> PodcastScript | None:
    return (await db.execute(
        select(PodcastScript).where(
            PodcastScript.document_id == document_id,
            PodcastScript.unit_index == unit_index,
        )
    )).scalars().first()


def _serialize(s: PodcastScript) -> dict:
    return {
        "id": s.id, "document_id": s.document_id, "unit_index": s.unit_index,
        "content": s.content, "status": s.status, "error": s.error,
        "has_audio": bool(s.audio_path),
        "audio_seconds": estimate_audio_seconds(s.content),
        "updated_at": s.updated_at.isoformat(),
    }


# ---------------------------------------------------------------- 文稿

@router.post("/{document_id}/script")
async def generate_script(document_id: str, unit_index: int = 0, db: AsyncSession = Depends(get_db)):
    """生成某阅读单元的播客文稿（同步返回，status=done/error）。"""
    doc = await _get_doc(db, document_id)
    script = await generate_podcast_script(db, doc, unit_index)
    return _serialize(script)


@router.get("/{document_id}/script")
async def get_script(document_id: str, unit_index: int = 0, db: AsyncSession = Depends(get_db)):
    """查询某阅读单元的播客文稿（无记录时返回 status=none）。"""
    await _get_doc(db, document_id)
    script = await _get_script(db, document_id, unit_index)
    if not script:
        return {"id": None, "document_id": document_id, "unit_index": unit_index,
                "content": "", "status": "none", "error": "", "has_audio": False,
                "audio_seconds": 0, "updated_at": None}
    return _serialize(script)


# ---------------------------------------------------------------- 音频

@router.post("/{document_id}/audio")
async def generate_audio(document_id: str, unit_index: int = 0, db: AsyncSession = Depends(get_db)):
    """基于已生成文稿合成播客音频（同步返回，成功后可用 GET audio 试听/下载）。"""
    await _get_doc(db, document_id)
    script = await _get_script(db, document_id, unit_index)
    if not script or not script.content or script.status != "done":
        raise HTTPException(status_code=400, detail="请先生成播客文稿")
    try:
        script = await script_to_audio(db, script)
    except TTSNotConfiguredError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except TTSError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.exception("播客音频生成失败 doc=%s unit=%s", document_id, unit_index)
        raise HTTPException(status_code=500, detail=f"音频生成失败：{str(e)[:200]}")
    return _serialize(script)


@router.get("/{document_id}/audio")
async def get_audio(document_id: str, unit_index: int = 0, db: AsyncSession = Depends(get_db)):
    """流式返回播客音频文件（mp3）。"""
    await _get_doc(db, document_id)
    script = await _get_script(db, document_id, unit_index)
    if not script or not script.audio_path or not Path(script.audio_path).exists():
        raise HTTPException(status_code=404, detail="音频不存在，请先生成")
    media_type = "audio/wav" if script.audio_path.lower().endswith(".wav") else "audio/mpeg"
    return FileResponse(
        script.audio_path, media_type=media_type,
        filename=f"podcast_{document_id[:8]}_unit{unit_index}.mp3",
    )
