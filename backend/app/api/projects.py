"""学习项目（书架中的书）API：项目 CRUD、章节列表、章节排序、级联删除、整书导入."""
import json
import logging
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import (
    Project, Document, Chunk, KnowledgePoint, Question, Flashcard, Annotation, DocSummary,
)
from app.api.documents import delete_document_cascade, ALLOWED_EXT
from app.core.book_split import (
    count_pdf_pages, extract_page_texts, find_toc_pages, extract_toc_entries, infer_toc_from_book,
    infer_toc_from_scan, scan_chapter_headings,
    calibrate_page_offset, build_chapter_ranges, _leaf_count, _ensure_front_matter,
    create_chapter_documents, create_chapter_from_book, reslice_chapter, cleanup_orphan_book_files,
)
from app.core.parsing import parse_file, chunk_text
from app.core.voice_agent import run_agent_turn

logger = logging.getLogger("yuanqi.api.projects")
router = APIRouter(prefix="/api/projects", tags=["projects"])

LOCAL_USER_ID = "local_user"

# 整书原文件命名：book_<8hex>_<原始文件名>.pdf（见 import_book）
_BOOK_FILE_RE = re.compile(r"^book_[0-9a-f]{8}_(.+)$")


def _book_display_title(book_path: str) -> str:
    """从整书原文件名解析展示名（原始上传文件名），避免用第一章标题代替书名。"""
    name = Path(book_path).name
    m = _BOOK_FILE_RE.match(name)
    stem = Path(m.group(1) if m else name).stem
    return stem[:128] or name[:128]


class ProjectIn(BaseModel):
    title: str
    description: str = ""
    icon: str = "📚"


class ProjectUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    icon: str | None = None


class ReorderIn(BaseModel):
    document_ids: list[str]


@router.get("")
async def list_projects(db: AsyncSession = Depends(get_db)):
    projects = (await db.execute(select(Project).order_by(Project.created_at))).scalars().all()
    counts = dict((await db.execute(
        select(Document.project_id, func.count())
        .where(Document.project_id.is_not(None), Document.content_type != "group")
        .group_by(Document.project_id)
    )).all())
    return [{
        "id": p.id, "title": p.title, "description": p.description, "icon": p.icon,
        "document_count": int(counts.get(p.id, 0)),
        "created_at": p.created_at.isoformat(),
    } for p in projects]


@router.post("")
async def create_project(data: ProjectIn, db: AsyncSession = Depends(get_db)):
    title = data.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="项目名称不能为空")
    p = Project(user_id=LOCAL_USER_ID, title=title,
                description=data.description or "", icon=data.icon or "📚")
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return {"id": p.id, "title": p.title, "description": p.description,
            "icon": p.icon, "document_count": 0, "created_at": p.created_at.isoformat()}


@router.get("/{project_id}")
async def get_project(project_id: str, db: AsyncSession = Depends(get_db)):
    p = await db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    docs = (await db.execute(
        select(Document).where(Document.project_id == project_id)
        .order_by(Document.sort_order, Document.created_at)
    )).scalars().all()
    counts = await _feature_counts(db, [d.id for d in docs])

    # 多书元数据：按 book_file_path 聚合，每本整书给一个参考章节 id + 总页数 + 章节数
    book_order: dict[str, dict] = {}
    for d in docs:
        if d.book_file_path and d.book_file_path not in book_order:
            book_order[d.book_file_path] = {"ref_id": d.id,
                                            "title": _book_display_title(d.book_file_path), "count": 0}
        if d.book_file_path in book_order:
            book_order[d.book_file_path]["count"] += 1
    books = []
    book_total = None
    for path, info in book_order.items():
        total = None
        if Path(path).exists():
            try:
                total = count_pdf_pages(path)
            except Exception:
                pass
        if book_total is None:
            book_total = total
        books.append({"ref_document_id": info["ref_id"], "title": info["title"],
                      "total_pages": total, "chapter_count": info["count"]})
    ref_by_path = {path: info["ref_id"] for path, info in book_order.items()}

    return {
        "project": {"id": p.id, "title": p.title, "description": p.description,
                    "icon": p.icon, "created_at": p.created_at.isoformat(),
                    "book_total_pages": book_total,
                    "books": books},
        "documents": [_serialize_doc(d, counts.get(d.id, {}), ref_by_path.get(d.book_file_path)) for d in docs],
    }


@router.put("/{project_id}")
async def update_project(project_id: str, data: ProjectUpdate, db: AsyncSession = Depends(get_db)):
    p = await db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    if data.title is not None:
        if not data.title.strip():
            raise HTTPException(status_code=400, detail="项目名称不能为空")
        p.title = data.title.strip()
    if data.description is not None:
        p.description = data.description
    if data.icon is not None:
        p.icon = data.icon
    await db.commit()
    await db.refresh(p)
    return {"id": p.id, "title": p.title, "description": p.description,
            "icon": p.icon, "created_at": p.created_at.isoformat()}


@router.delete("/{project_id}")
async def delete_project(project_id: str, db: AsyncSession = Depends(get_db)):
    p = await db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    # 收集该项目引用的整书文件，删除章节后清理不再被引用的孤儿整书
    book_paths = set((await db.execute(
        select(Document.book_file_path).where(
            Document.project_id == project_id, Document.book_file_path.is_not(None))
    )).scalars().all())
    doc_ids = (await db.execute(select(Document.id).where(Document.project_id == project_id))).scalars().all()
    for did in doc_ids:
        await delete_document_cascade(db, did)
    await db.execute(delete(Project).where(Project.id == project_id))
    await db.commit()
    for bp in book_paths:
        await cleanup_orphan_book_files(db, bp)
    return {"ok": True, "deleted_documents": len(doc_ids)}


@router.post("/{project_id}/reorder")
async def reorder_documents(project_id: str, data: ReorderIn, db: AsyncSession = Depends(get_db)):
    """章节排序：按 document_ids 顺序写入 sort_order。"""
    p = await db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    existing = set((await db.execute(
        select(Document.id).where(Document.project_id == project_id)
    )).scalars().all())
    for i, did in enumerate(data.document_ids):
        if did in existing:
            d = await db.get(Document, did)
            if d:
                d.sort_order = i
    await db.commit()
    return {"ok": True}


@router.post("/{project_id}/import-book")
async def import_book(
    project_id: str,
    file: UploadFile = File(...),
    start_page: int | None = Form(None),
    end_page: int | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """导入整书 PDF（可指定页码范围分批导入）：识别目录 → 依据目录切成多个章节。

    请求：multipart file + start_page/end_page（1 基，可选，默认全书）。
    SSE 事件：
      {"type":"toc","status":"detecting"|"done","source":"toc_page"|"llm_inferred",
       "entries":[{level,title,page_number}],"message":str}
      {"type":"chapter","title":str,"message":str}          // 每创建一章发一次
      {"type":"done","chapters":[...],"warnings":[...],"message":str}
      {"type":"error","message":str}                        // 退化/失败时明确报错
    """
    p = await db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="整书导入仅支持 PDF")
    content = await file.read()
    if len(content) > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件过大")

    # 保存原书（留档，不建 Document）
    save_dir = Path(settings.document_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    book_path = save_dir / f"book_{uuid.uuid4().hex[:8]}_{Path(filename).name}"
    book_path.write_bytes(content)
    book_title = Path(filename).stem[:128]

    async def event_stream():
        try:
            total = count_pdf_pages(book_path)
            sp = max(1, start_page or 1)
            ep = min(total, end_page or total)
            if sp > ep:
                yield _sse({"type": "error", "message": f"页码范围无效：起始页 {sp} 大于结束页 {ep}"})
                return
            range_start_idx = sp - 1  # 0 基物理页
            is_full_range = sp <= 1 and ep >= total
            yield _sse({"type": "toc", "status": "detecting",
                        "message": f"正在识别目录…（共 {total} 页，本次导入第 {sp}-{ep} 页）"})

            text_pages = extract_page_texts(book_path, start_page=sp, end_page=ep)

            # 1) 目录页优先：候选按分数降序；合并多个目录页（厚书目录常跨 2-3 页），
            #    按印刷页码去重，避免只读第一页目录导致尾部章节（第二页起）被漏掉。
            toc_candidates = find_toc_pages(text_pages, total_pages=total)
            entries: list[dict] = []
            source = "toc_page"
            merged: dict[int, str] = {}
            for c in toc_candidates[:3]:
                page_entries = await extract_toc_entries(text_pages[c], book_title, total)
                if not page_entries:
                    continue
                for e in page_entries:
                    merged.setdefault(int(e["page_number"]), str(e["title"]))
            entries = [{"level": 1, "title": t, "page_number": p}
                       for p, t in sorted(merged.items())]
            # 2) 无目录页 → 全书扫描章节标题行 + LLM 整理（比采样前30页可靠得多）
            if not entries:
                source = "llm_inferred"
                scan = scan_chapter_headings(book_path, total, start_page=sp, end_page=ep)
                entries = await infer_toc_from_scan(scan, book_title, total)
            # 3) 最后兜底：LLM 采样归纳
            if not entries:
                source = "llm_inferred"
                sample = "\n\n".join(text_pages[:30])[:5000]
                entries = await infer_toc_from_book(sample, book_title, total)
            if not entries:
                yield _sse({"type": "error", "message": "未能识别出章节目录，请改用「导入章节」单章导入"})
                return

            yield _sse({"type": "toc", "status": "done", "source": source,
                        "entries": entries, "message": f"识别到 {len(entries)} 个章节"})

            # 3) 页码校准 + 章节范围（含校验告警）+ 退化检测
            #    目录页来源用印刷页码校准；扫描/归纳来源给出的已是（近似）物理页，offset 取 0
            offset = calibrate_page_offset(book_path, text_pages, entries, range_start_idx) \
                if source == "toc_page" else 0
            ranges, warnings = build_chapter_ranges(len(text_pages), entries, offset, range_start_idx)
            if not ranges:
                yield _sse({"type": "error", "message": "目录条目无法映射到页面，未生成任何章节"})
                return
            # 正文前的实质内容（前言/序等）兜底补成一章，放在章节数判定前
            ranges = _ensure_front_matter(ranges, text_pages, range_start_idx, warnings)
            if is_full_range and _leaf_count(ranges) < 2:
                yield _sse({"type": "error",
                            "message": "目录识别失败：仅识别到 1 个章节，未分章。请重试或改用「导入章节」单章导入"})
                return

            base_sort = await _next_project_sort_order(db, project_id)
            docs = await create_chapter_documents(db, project_id, book_path, ranges, base_sort_order=base_sort)
            for d in docs:
                yield _sse({"type": "chapter", "title": d.chapter_title or d.title,
                            "message": f"章节「{d.chapter_title or d.title}」已创建"})
            leaf = sum(1 for d in docs if d.content_type != "group")
            grp = sum(1 for d in docs if d.content_type == "group")
            msg = f"已切成 {leaf} 个章节" + (f"、{grp} 个分组" if grp else "")
            yield _sse({"type": "done",
                        "chapters": [{"id": d.id, "title": d.title,
                                      "chapter_title": d.chapter_title or "",
                                      "sort_order": d.sort_order, "chunk_count": d.chunk_count}
                                     for d in docs],
                        "warnings": warnings,
                        "message": msg})
        except Exception as e:
            logger.exception("import-book failed")
            yield _sse({"type": "error", "message": f"整书导入失败：{str(e)[:200]}"})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ---------------------------------------------------------------- 手动建章 / 调节 / 上传

class ChapterCreate(BaseModel):
    mode: str = "blank"                   # blank（空白占位） / slice（划页建章）
    title: str = ""
    source_document_id: str | None = None  # slice：整书拆分章节（含 book_file_path）
    page_start: int | None = None          # slice：起始页（1 基）
    page_end: int | None = None            # slice：结束页（1 基）


@router.post("/{project_id}/chapters")
async def create_chapter(project_id: str, data: ChapterCreate, db: AsyncSession = Depends(get_db)):
    """手动新建章节：空白占位 或 从整书按页切片。"""
    p = await db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    title = data.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="章节标题不能为空")
    sort_order = await _next_project_sort_order(db, project_id)

    if data.mode == "blank":
        doc = Document(user_id=LOCAL_USER_ID, title=title, filename="", file_path="",
                       content_type="blank", chunk_count=0,
                       project_id=project_id, chapter_title=title, sort_order=sort_order)
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        return _serialize_doc(doc, {})
    if data.mode == "slice":
        if data.source_document_id is None or data.page_start is None or data.page_end is None:
            raise HTTPException(status_code=400, detail="划页建章需要 source_document_id 与起始/结束页")
        src = await db.get(Document, data.source_document_id)
        if not src or src.project_id != project_id or not src.book_file_path:
            raise HTTPException(status_code=400, detail="源文档不是整书拆分的章节（无整书引用）")
        total = count_pdf_pages(src.book_file_path)
        ps, pe = data.page_start - 1, data.page_end - 1
        if ps < 0 or pe >= total or ps > pe:
            raise HTTPException(status_code=400, detail=f"页码越界或非法：应在 1-{total} 之间且起始≤结束")
        doc = await create_chapter_from_book(db, project_id, src.book_file_path, title, ps, pe, sort_order)
        return _serialize_doc(doc, {})
    raise HTTPException(status_code=400, detail="mode 须为 blank 或 slice")


class ChapterRange(BaseModel):
    document_id: str | None = None
    title: str = ""
    page_start: int = 0
    page_end: int = 0
    # 新章节（document_id 为空）的来源整书参考章节：取其 book_file_path 作为该书路径
    source_document_id: str | None = None


class ChaptersSyncIn(BaseModel):
    chapters: list[ChapterRange]


@router.post("/{project_id}/chapters/sync")
async def sync_chapters(project_id: str, data: ChaptersSyncIn, db: AsyncSession = Depends(get_db)):
    """章节分页调节器 reconcile（支持多本整书混排）：
    列表内已有章节重切、新增章节切片、按来源书维度级联删除列表缺失章节、按列表序重排 sort_order。

    相邻章节范围允许重叠（边界页可同时归属两章）；每章页码按各自来源书总页数校验。
    """
    p = await db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    existing = (await db.execute(
        select(Document).where(Document.project_id == project_id)
    )).scalars().all()
    by_id = {d.id: d for d in existing}
    book_docs = [d for d in existing if d.book_file_path]
    if not book_docs:
        raise HTTPException(status_code=400, detail="该项目没有可从整书切分的章节（无整书引用）")

    # 每行解析来源书路径：已有章节取自身 book_file_path；新增章节取 source_document_id 的
    rows: list[dict] = []
    for i, c in enumerate(data.chapters):
        book_path: str | None = None
        if c.document_id and c.document_id in by_id and by_id[c.document_id].book_file_path:
            book_path = by_id[c.document_id].book_file_path
        elif c.source_document_id and c.source_document_id in by_id and by_id[c.source_document_id].book_file_path:
            book_path = by_id[c.source_document_id].book_file_path
        if not book_path:
            raise HTTPException(status_code=400,
                                detail=f"章节「{c.title or '(未命名)'}」无法确定来源整书")
        rows.append({
            "document_id": c.document_id, "title": c.title, "page_start": c.page_start,
            "page_end": c.page_end, "book_path": book_path,
        })

    # 每章按各自来源书校验页码
    for r in rows:
        if not Path(r["book_path"]).exists():
            raise HTTPException(status_code=400,
                                detail=f"章节「{r['title']}」来源整书文件不存在")
        total = count_pdf_pages(r["book_path"])
        if r["page_start"] < 0 or r["page_end"] >= total or r["page_start"] > r["page_end"]:
            raise HTTPException(
                status_code=400,
                detail=f"章节「{r['title'] or '(未命名)'}」页码范围非法："
                       f"{r['page_start'] + 1}-{r['page_end'] + 1}，应在 1-{total} 且起始≤结束",
            )

    # 按来源书维度：只删除该书下未出现在新列表中的章节，不误删其他整书章节
    rows_by_book: dict[str, list[dict]] = {}
    for r in rows:
        rows_by_book.setdefault(r["book_path"], []).append(r)
    for d in book_docs:
        listed = {r["document_id"] for r in rows_by_book.get(d.book_file_path, []) if r["document_id"]}
        if d.id not in listed:
            await delete_document_cascade(db, d.id)
    await db.commit()

    # 按列表序：已有重切 / 新增切片，写 sort_order（多书混排也按整体顺序续接）
    for i, r in enumerate(rows):
        title = r["title"].strip() or f"第 {i + 1} 章"
        if r["document_id"] and r["document_id"] in by_id and by_id[r["document_id"]].book_file_path:
            doc = by_id[r["document_id"]]
            await reslice_chapter(db, doc, r["book_path"], r["page_start"], r["page_end"], title)
            doc.sort_order = i
            await db.commit()
        else:
            await create_chapter_from_book(db, project_id, r["book_path"], title,
                                           r["page_start"], r["page_end"], i)

    # 清理所有涉及来源书的孤儿整书文件
    all_books = {d.book_file_path for d in book_docs} | set(rows_by_book.keys())
    for bp in all_books:
        await cleanup_orphan_book_files(db, bp)
    return await get_project(project_id, db)


@router.post("/{project_id}/chapters/{document_id}/attach")
async def attach_chapter_file(
    project_id: str,
    document_id: str,
    file: UploadFile = File(...),
    chapter_title: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """给空白章节上传资料：替换占位文件并重新解析分块。"""
    doc = await db.get(Document, document_id)
    if not doc or doc.project_id != project_id:
        raise HTTPException(status_code=404, detail="章节不存在")
    if doc.content_type != "blank":
        raise HTTPException(status_code=400, detail="仅空白章节可上传资料（新建章节请用「导入章节」）")
    filename = file.filename or "unnamed"
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400,
                            detail=f"不支持的文件类型：{ext}（支持 {sorted(ALLOWED_EXT)}）")
    content = await file.read()
    if len(content) > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件过大")

    save_dir = Path(settings.document_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    file_path = save_dir / f"{document_id}_attach{ext}"
    file_path.write_bytes(content)

    text, hints = parse_file(file_path)
    chunks_data = chunk_text(text, hints)
    await db.execute(delete(Chunk).where(Chunk.document_id == document_id))
    for i, c in enumerate(chunks_data):
        db.add(Chunk(document_id=document_id, seq=i, content=c["content"], heading=c["heading"]))

    doc.file_path = str(file_path)
    doc.filename = filename
    doc.content_type = ext.lstrip(".")
    doc.chunk_count = len(chunks_data)
    if chapter_title and chapter_title.strip():
        doc.chapter_title = chapter_title.strip()
    await db.commit()
    await db.refresh(doc)
    counts = await _feature_counts(db, [doc.id])
    return _serialize_doc(doc, counts.get(doc.id, {}))


class GroupIn(BaseModel):
    title: str = ""
    chapter_ids: list[str] = []


@router.post("/{project_id}/groups")
async def create_group(project_id: str, data: GroupIn, db: AsyncSession = Depends(get_db)):
    """新建分组（部分/卷）：可把指定章节纳入分组，并据其页范围回填分组覆盖范围。"""
    p = await db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    title = data.title.strip() or "新分组"
    sort_order = await _next_project_sort_order(db, project_id)
    children: list[Document] = []
    if data.chapter_ids:
        children = (await db.execute(
            select(Document).where(Document.id.in_(data.chapter_ids),
                                   Document.project_id == project_id,
                                   Document.content_type != "group")
        )).scalars().all()
    ps = min((c.page_start for c in children if c.page_start is not None), default=None)
    pe = max((c.page_end for c in children if c.page_end is not None), default=None)
    grp = Document(user_id=LOCAL_USER_ID, title=title, filename="", file_path="",
                   content_type="group", chunk_count=0, project_id=project_id,
                   chapter_title=title, sort_order=sort_order, page_start=ps, page_end=pe)
    db.add(grp)
    await db.flush()
    for c in children:
        c.parent_id = grp.id
    await db.commit()
    await db.refresh(grp)
    return _serialize_doc(grp, {})


class AgentIn(BaseModel):
    message: str
    history: list[dict[str, str]] = []


@router.post("/{project_id}/agent")
async def project_agent(project_id: str, data: AgentIn, db: AsyncSession = Depends(get_db)):
    """语音助手：对话 + 提议章节目录修改（SSE）。

    SSE 事件：
      {"type":"delta","content":str}               // 助手回复（已剥离 EDIT 块）
      {"type":"edit_proposal","proposal":{...}}    // 提议的章节修改（前端展示，应用/弃用）
      {"type":"done"}
    """
    try:
        result = await run_agent_turn(db, project_id, data.message, data.history)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("voice agent failed")
        raise HTTPException(status_code=500, detail=f"语音助手调用失败：{str(e)[:200]}")

    async def event_stream():
        yield _sse({"type": "delta", "content": result["reply"]})
        if result.get("proposal"):
            yield _sse({"type": "edit_proposal", "proposal": result["proposal"]})
        yield _sse({"type": "done"})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


async def _next_project_sort_order(db: AsyncSession, project_id: str) -> int:
    """项目内下一个 sort_order（当前最大值 + 1），供分批导入续接排序。"""
    max_order = (await db.execute(
        select(func.coalesce(func.max(Document.sort_order), -1)).where(Document.project_id == project_id)
    )).scalar()
    return int(max_order) + 1


async def _feature_counts(db: AsyncSession, doc_ids: list[str]) -> dict[str, dict]:
    """每个文档的知识树/题目/闪卡/批注/总结数量，用于前端功能入口置灰。"""
    result: dict[str, dict] = {}
    if not doc_ids:
        return result
    for model in (KnowledgePoint, Question, Flashcard, Annotation, DocSummary):
        rows = (await db.execute(
            select(model.document_id, func.count()).where(model.document_id.in_(doc_ids)).group_by(model.document_id)
        )).all()
        for did, n in rows:
            result.setdefault(did, {})[model.__tablename__] = int(n)
    return result


def _serialize_doc(d: Document, counts: dict, book_ref_id: str | None = None) -> dict:
    return {
        "id": d.id, "title": d.title, "filename": d.filename,
        "content_type": d.content_type, "chunk_count": d.chunk_count,
        "chapter_title": d.chapter_title or "", "sort_order": d.sort_order,
        # 目录层级：分组节点(content_type='group') 无文件；章节的 parent_id 指向所属分组
        "parent_id": d.parent_id,
        "is_group": d.content_type == "group",
        # 整书引用与物理页范围（0 基）；blank 占位章节无 file
        "book_file": bool(d.book_file_path),
        "book_ref_document_id": book_ref_id,  # 该书参考章节 id（供调节器/预览定位整书）
        "page_start": d.page_start,
        "page_end": d.page_end,
        "knowledge_count": counts.get("knowledge_points", 0),
        "question_count": counts.get("questions", 0),
        "flashcard_count": counts.get("flashcards", 0),
    }
