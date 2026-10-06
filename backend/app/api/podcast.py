"""AI 播客 API — 文稿生成/查询、音频生成/获取.

对标豆包 AI 播客：每个阅读单元（章节/页）独立成一条播客。
流程：生成文稿（可查看/重新生成）→ 生成音频 → 试听/下载。
"""
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_optional_user
from app.database import get_db
from app.core.podcast import (
    generate_podcast_script, edit_podcast_script, update_podcast_script, undo_podcast_script,
)
from app.core.podcast_tts import (
    TTSNotConfiguredError, TTSError, estimate_audio_seconds, resolve_tts_context,
    script_to_audio,
)
from app.core.reading_content import get_reading_units
from app.models import Document, PodcastScript, User

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
        "can_undo": bool(s.prev_content),  # 是否有可撤回的上一步
        "audio_seconds": s.audio_seconds if s.audio_seconds else estimate_audio_seconds(s.content),
        "updated_at": s.updated_at.isoformat(),
    }


# ---------------------------------------------------------------- 播客库（列表 / 删除）

@router.get("/list")
async def list_podcasts(db: AsyncSession = Depends(get_db)):
    """播客库：全部已生成的播客文稿（含文档名、单元标题、音频状态）。

    供「我的播客」页面整理使用：播放/删除/重新生成。
    """
    scripts = (await db.execute(
        select(PodcastScript).order_by(PodcastScript.updated_at.desc())
    )).scalars().all()
    if not scripts:
        return {"count": 0, "podcasts": []}

    doc_ids = {s.document_id for s in scripts}
    docs = (await db.execute(select(Document).where(Document.id.in_(doc_ids)))).scalars().all()
    doc_map = {d.id: d for d in docs}

    # 解析每本有播客的文档的单元标题（懒加载，少量文档可接受）
    unit_titles: dict[tuple[str, int], str] = {}
    for doc in docs:
        try:
            units = await get_reading_units(db, doc)
            for u in units:
                unit_titles[(doc.id, u["index"])] = u["title"]
        except Exception:
            pass

    items = []
    for s in scripts:
        doc = doc_map.get(s.document_id)
        items.append({
            "id": s.id, "document_id": s.document_id, "unit_index": s.unit_index,
            "doc_title": doc.title if doc else "(已删除文档)",
            "unit_title": unit_titles.get((s.document_id, s.unit_index),
                                          f"第 {s.unit_index + 1} 单元"),
            "content": s.content, "status": s.status, "error": s.error,
            "has_audio": bool(s.audio_path),
            "audio_seconds": s.audio_seconds if s.audio_seconds else estimate_audio_seconds(s.content),
            "updated_at": s.updated_at.isoformat(),
        })
    return {"count": len(items), "podcasts": items}


@router.delete("/{document_id}")
async def delete_podcast(document_id: str, unit_index: int = 0, db: AsyncSession = Depends(get_db)):
    """删除某期播客（文稿 + 音频文件）。"""
    await _get_doc(db, document_id)
    script = await _get_script(db, document_id, unit_index)
    if not script:
        raise HTTPException(status_code=404, detail="播客不存在")
    audio_path = script.audio_path
    await db.execute(delete(PodcastScript).where(PodcastScript.id == script.id))
    await db.commit()
    if audio_path:
        try:
            Path(audio_path).unlink(missing_ok=True)
        except Exception as e:
            logger.warning("删除播客音频失败: %s", e)
    return {"ok": True}


# ---------------------------------------------------------------- 文稿

class EditScriptIn(BaseModel):
    instruction: str


class UpdateScriptIn(BaseModel):
    content: str


@router.put("/{document_id}/script")
async def save_script(document_id: str, data: UpdateScriptIn,
                      unit_index: int = 0, db: AsyncSession = Depends(get_db)):
    """手动直接保存文稿内容（不经 AI）。改后旧音频作废，需重新合成。"""
    content = (data.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="文稿不能为空")
    doc = await _get_doc(db, document_id)
    try:
        script = await update_podcast_script(db, doc, unit_index, content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("播客文稿保存失败 doc=%s unit=%s", document_id, unit_index)
        raise HTTPException(status_code=500, detail=f"文稿保存失败：{str(e)[:200]}")
    return _serialize(script)


@router.post("/{document_id}/edit-script")
async def edit_script(document_id: str, data: EditScriptIn,
                      unit_index: int = 0, db: AsyncSession = Depends(get_db)):
    """按用户指令（打字/语音）修改播客文稿。改后旧音频作废，需重新合成。"""
    instruction = (data.instruction or "").strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="请输入修改要求")
    doc = await _get_doc(db, document_id)
    try:
        script = await edit_podcast_script(db, doc, unit_index, instruction)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("播客文稿修改失败 doc=%s unit=%s", document_id, unit_index)
        raise HTTPException(status_code=500, detail=f"文稿修改失败：{str(e)[:200]}")
    return _serialize(script)


@router.post("/{document_id}/undo-script")
async def undo_script(document_id: str, unit_index: int = 0, db: AsyncSession = Depends(get_db)):
    """撤回上一步修改：恢复上次修改前的文稿。"""
    doc = await _get_doc(db, document_id)
    try:
        script = await undo_podcast_script(db, doc, unit_index)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("播客文稿撤回失败 doc=%s unit=%s", document_id, unit_index)
        raise HTTPException(status_code=500, detail=f"撤回失败：{str(e)[:200]}")
    return _serialize(script)


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
async def generate_audio(document_id: str, unit_index: int = 0,
                         db: AsyncSession = Depends(get_db),
                         user: User | None = Depends(get_optional_user)):
    """基于已生成文稿合成播客音频（同步返回，成功后可用 GET audio 试听/下载）。"""
    await _get_doc(db, document_id)
    script = await _get_script(db, document_id, unit_index)
    if not script or not script.content or script.status != "done":
        raise HTTPException(status_code=400, detail="请先生成播客文稿")
    try:
        script = await script_to_audio(
            db, script, tts_ctx=await resolve_tts_context(db, user.id if user else None))
    except TTSNotConfiguredError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except TTSError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.exception("播客音频生成失败 doc=%s unit=%s", document_id, unit_index)
        raise HTTPException(status_code=500, detail=f"音频生成失败：{str(e)[:200]}")
    return _serialize(script)


@router.get("/{document_id}/audio")
async def get_audio(document_id: str, request: Request,
                    unit_index: int = 0, db: AsyncSession = Depends(get_db)):
    """流式返回播客音频文件（mp3），支持 HTTP Range（浏览器拖动进度条必需）。"""
    await _get_doc(db, document_id)
    script = await _get_script(db, document_id, unit_index)
    if not script or not script.audio_path or not Path(script.audio_path).exists():
        raise HTTPException(status_code=404, detail="音频不存在，请先生成")
    media_type = "audio/wav" if script.audio_path.lower().endswith(".wav") else "audio/mpeg"
    return _serve_audio_range(Path(script.audio_path), media_type, request)


def _serve_audio_range(path: Path, media_type: str, request: Request) -> Response:
    """支持 Range 请求的音频响应：正常 200 全量；带 Range 头返回 206 分段。

    浏览器/播放器依赖 206 + Content-Range 才能拖动进度条、正确显示总时长。
    """
    size = path.stat().st_size
    start, end = 0, size - 1
    status = 200

    range_header = request.headers.get("range", "")
    if range_header.startswith("bytes="):
        spec = range_header[len("bytes="):].split(",", 1)[0].strip()
        if "-" in spec:
            a, b = spec.split("-", 1)
            try:
                if a == "":
                    # 后缀范围：bytes=-N → 最后 N 字节
                    n = int(b)
                    start = max(0, size - n)
                else:
                    start = int(a)
                    if b != "":
                        end = min(int(b), size - 1)
                if start > end or start >= size:
                    return Response(status_code=416,
                                    headers={"Content-Range": f"bytes */{size}"})
                status = 206
            except ValueError:
                status = 200

    with path.open("rb") as f:
        f.seek(start)
        content = f.read(end - start + 1)

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Type": media_type,
        "Content-Length": str(len(content)),
        "Content-Disposition": f'inline; filename="{path.name}"',
    }
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return Response(content=content, status_code=status, headers=headers)
