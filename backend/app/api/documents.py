"""文档 API — 上传（可归属项目章节）、解析分块、列表、更新、删除."""
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db, ensure_default_project
from app.core.parsing import parse_file, chunk_text, estimate_tokens
from app.models import (
    Document, Chunk, User, KnowledgePoint, Question, Flashcard,
    Annotation, DocSummary, QuizRecord, Project, PodcastScript, Drawing, BlankCache,
)

logger = logging.getLogger("yuanqi.api.documents")
router = APIRouter(prefix="/api/documents", tags=["documents"])

LOCAL_USER_ID = "local_user"

ALLOWED_EXT = {".pdf", ".docx", ".md", ".markdown", ".txt", ".pptx"}


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    project_id: str | None = Form(None),
    chapter_title: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Upload a document, parse it into chunks, and return chunk ids.

    可归属到某个项目（project_id）作为其章节；未指定则归入「未分类」默认项目。
    """
    filename = file.filename or "unnamed"
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型：{ext}（支持 {sorted(ALLOWED_EXT)}）")

    content = await file.read()
    if len(content) > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件过大")

    # Save to disk
    doc_id = str(uuid.uuid4())
    safe_name = Path(filename).name
    save_dir = Path(settings.document_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    file_path = save_dir / f"{doc_id}_{safe_name}"
    file_path.write_bytes(content)

    title = Path(safe_name).stem[:250]
    chapter_title = (chapter_title or "").strip() or None

    # 归属项目：未指定则归入「未分类」默认项目
    if not project_id:
        default = await ensure_default_project(db)
        project_id = default.id
    sort_order = await _next_sort_order(db, project_id)

    try:
        doc, chunk_objs = await ingest_document_file(
            db, file_path, title=title,
            project_id=project_id, chapter_title=chapter_title, sort_order=sort_order,
        )
    except Exception as e:
        file_path.unlink(missing_ok=True)
        logger.warning("ingest failed for %s: %s", filename, e)
        raise HTTPException(status_code=400, detail=f"文档解析失败：{e}")

    return {
        "id": doc.id, "title": doc.title, "filename": doc.filename,
        "content_type": doc.content_type, "chunk_count": doc.chunk_count,
        "project_id": doc.project_id, "chapter_title": doc.chapter_title,
        "sort_order": doc.sort_order,
        "chunks": [{"id": c.id, "seq": c.seq, "heading": c.heading,
                    "content": c.content, "tokens": estimate_tokens(c.content)}
                   for c in chunk_objs],
    }


async def ingest_document_file(
    db: AsyncSession,
    file_path: Path,
    title: str,
    project_id: str,
    chapter_title: str | None = None,
    sort_order: int = 0,
) -> tuple[Document, list[Chunk]]:
    """解析磁盘文件并落库为 Document + Chunks，返回 (doc, chunk_objs)（已 commit）。

    供单章上传与整书分章（book_split.create_chapter_documents）共用。
    """
    text, hints = parse_file(file_path)
    chunks_data = chunk_text(text, hints)
    doc_id = str(uuid.uuid4())
    ext = file_path.suffix.lower().lstrip(".")

    doc = Document(
        id=doc_id, user_id=LOCAL_USER_ID, title=title, filename=file_path.name,
        file_path=str(file_path), content_type=ext, chunk_count=len(chunks_data),
        project_id=project_id, chapter_title=chapter_title, sort_order=sort_order,
    )
    db.add(doc)
    await db.flush()  # 先写父文档，保证 chunks 外键可满足
    chunk_objs: list[Chunk] = []
    for i, c in enumerate(chunks_data):
        co = Chunk(document_id=doc_id, seq=i, content=c["content"], heading=c["heading"])
        db.add(co)
        chunk_objs.append(co)
    await db.flush()  # 让 chunk id 生成
    await db.commit()
    await db.refresh(doc)
    return doc, chunk_objs


@router.get("")
async def list_documents(project_id: str | None = None, db: AsyncSession = Depends(get_db)):
    """列出文档。可传 project_id 只列某项目；不传则列全部。"""
    stmt = select(Document).order_by(Document.project_id, Document.sort_order, Document.created_at)
    if project_id:
        stmt = select(Document).where(Document.project_id == project_id).order_by(Document.sort_order, Document.created_at)
    docs = (await db.execute(stmt)).scalars().all()
    return [{
        "id": d.id, "title": d.title, "filename": d.filename,
        "content_type": d.content_type, "chunk_count": d.chunk_count,
        "project_id": d.project_id, "chapter_title": d.chapter_title,
        "sort_order": d.sort_order, "created_at": d.created_at.isoformat(),
    } for d in docs]


class DocumentUpdate(BaseModel):
    title: str | None = None
    chapter_title: str | None = None
    project_id: str | None = None
    # 目录层级：把章节移入/移出分组（传 null 表示移到顶层）；仅当字段出现时生效
    parent_id: str | None = None


@router.put("/{doc_id}")
async def update_document(doc_id: str, data: DocumentUpdate, db: AsyncSession = Depends(get_db)):
    """编辑章节：改名 / 改章节标题 / 移入（出）项目。"""
    doc = await db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if data.title is not None:
        doc.title = data.title.strip() or doc.title
    if data.chapter_title is not None:
        doc.chapter_title = data.chapter_title.strip() or None
    if data.project_id is not None:
        new_pid = data.project_id or None
        if new_pid != doc.project_id:
            if new_pid:
                p = await db.get(Project, new_pid)
                if not p:
                    raise HTTPException(status_code=404, detail="目标项目不存在")
                doc.sort_order = await _next_sort_order(db, new_pid)
            doc.project_id = new_pid
    # 移入/移出分组（parent_id 出现在请求里才算，含显式 null=移到顶层）
    if "parent_id" in data.model_fields_set and data.parent_id != doc.parent_id:
        old_parent = doc.parent_id
        if data.parent_id:
            target = await db.get(Document, data.parent_id)
            if not target or target.content_type != "group" or target.project_id != doc.project_id:
                raise HTTPException(status_code=400, detail="目标分组不存在或不属于本项目")
        doc.parent_id = data.parent_id
        for gid in {old_parent, data.parent_id}:
            if gid:
                await _recompute_group_range(db, gid)
    await db.commit()
    await db.refresh(doc)
    return {
        "id": doc.id, "title": doc.title, "filename": doc.filename,
        "content_type": doc.content_type, "chunk_count": doc.chunk_count,
        "project_id": doc.project_id, "chapter_title": doc.chapter_title,
        "sort_order": doc.sort_order,
    }


async def _next_sort_order(db: AsyncSession, project_id: str) -> int:
    """项目内下一个 sort_order（当前最大值 + 1）。"""
    from sqlalchemy import func
    max_order = (await db.execute(
        select(func.coalesce(func.max(Document.sort_order), -1)).where(Document.project_id == project_id)
    )).scalar()
    return int(max_order) + 1  # coalesce 已把空集归一为 -1，勿用 `or -1`（0 会被当 falsy）


async def _recompute_group_range(db: AsyncSession, group_id: str) -> None:
    """根据分组下剩余章节的页范围回填分组的 page_start/page_end。"""
    group = await db.get(Document, group_id)
    if not group or group.content_type != "group":
        return
    children = (await db.execute(
        select(Document).where(Document.parent_id == group_id)
    )).scalars().all()
    ps = min((c.page_start for c in children if c.page_start is not None), default=None)
    pe = max((c.page_end for c in children if c.page_end is not None), default=None)
    group.page_start = ps
    group.page_end = pe
    await db.commit()


async def delete_document_cascade(db: AsyncSession, doc_id: str) -> None:
    """显式批量级联删除一份文档的全部关联数据。

    分组(部分/卷)删除会级联删除其下所有章节；删除章节后重算其原所属分组的覆盖范围。
    顺序保证外键安全（答题记录先于题目、知识树子节点先于父节点）；
    注意：ORM 逐行 delete 在 autoflush 下不可靠，务必使用批量 delete。
    """
    doc = await db.get(Document, doc_id)
    parent_id = doc.parent_id if doc else None
    # 分组 → 级联删除其下章节
    child_ids = (await db.execute(select(Document.id).where(Document.parent_id == doc_id))).scalars().all()
    for cid in child_ids:
        await delete_document_cascade(db, cid)
    q_ids = (await db.execute(select(Question.id).where(Question.document_id == doc_id))).scalars().all()
    if q_ids:
        await db.execute(delete(QuizRecord).where(QuizRecord.question_id.in_(q_ids)))
    await db.execute(delete(Chunk).where(Chunk.document_id == doc_id))
    # knowledge_points 自引用外键：先删子节点，再删全部
    kp_ids = (await db.execute(select(KnowledgePoint.id).where(KnowledgePoint.document_id == doc_id))).scalars().all()
    if kp_ids:
        await db.execute(delete(KnowledgePoint).where(
            KnowledgePoint.document_id == doc_id, KnowledgePoint.parent_id.in_(kp_ids)))
        await db.execute(delete(KnowledgePoint).where(KnowledgePoint.document_id == doc_id))
    await db.execute(delete(Question).where(Question.document_id == doc_id))
    await db.execute(delete(Flashcard).where(Flashcard.document_id == doc_id))
    await db.execute(delete(Annotation).where(Annotation.document_id == doc_id))
    await db.execute(delete(DocSummary).where(DocSummary.document_id == doc_id))
    # 播客文稿（含音频文件）
    pod_paths = (await db.execute(
        select(PodcastScript.audio_path).where(
            PodcastScript.document_id == doc_id, PodcastScript.audio_path.is_not(None))
    )).scalars().all()
    for pp in pod_paths:
        Path(pp).unlink(missing_ok=True)
    await db.execute(delete(PodcastScript).where(PodcastScript.document_id == doc_id))
    # 绘制批注（Drawing）、挖空缓存（BlankCache）
    await db.execute(delete(Drawing).where(Drawing.document_id == doc_id))
    await db.execute(delete(BlankCache).where(BlankCache.document_id == doc_id))
    doc = await db.get(Document, doc_id)
    if doc:
        # 分组/空白章节没有文件（file_path 为空），跳过 unlink
        if doc.file_path:
            Path(doc.file_path).unlink(missing_ok=True)
    await db.execute(delete(Document).where(Document.id == doc_id))
    # 删除章节后重算其原所属分组的覆盖范围（若还有剩余章节）
    if parent_id:
        await _recompute_group_range(db, parent_id)


@router.delete("/{doc_id}")
async def delete_document(doc_id: str, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    book_path = doc.book_file_path
    await delete_document_cascade(db, doc_id)
    await db.commit()
    # 若整书原文件不再被任何章节引用，清理孤儿文件
    if book_path:
        from app.core.book_split import cleanup_orphan_book_files
        await cleanup_orphan_book_files(db, book_path)
    return {"ok": True}


@router.get("/{doc_id}/file")
async def get_document_file(doc_id: str, db: AsyncSession = Depends(get_db)):
    """服务文档原文件（供阅读页原生视图 / 前端渲染用）。"""
    doc = await db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    path = Path(doc.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="原文件不存在")
    return FileResponse(path, filename=doc.filename or doc.title)


@router.get("/{doc_id}/book-file")
async def get_document_book_file(doc_id: str, db: AsyncSession = Depends(get_db)):
    """服务章节所属整书原文件（供章节内容预览用，含未切分的建议页码范围）。"""
    doc = await db.get(Document, doc_id)
    if not doc or not doc.book_file_path:
        raise HTTPException(status_code=404, detail="该章节无整书引用")
    path = Path(doc.book_file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="整书原文件不存在")
    return FileResponse(path, filename=Path(path).name)
