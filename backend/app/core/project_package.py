"""作品社区：项目导出 / 导入。

把一个「项目（书）」打包成 .yqp（zip）文件，可分享给社区、下载后重新导入。
导出内容：项目元数据 + 全部章节(文档) + 分块 + 知识树 + 题目 + 答题记录 + 闪卡
          + 批注 + 总结 + 播客文稿/音频 + 文档原文件 + 整书原文件。
导入：按格式重建项目（文档生成新 id，父子/内外键全部重映射）。

.zip 结构：
  manifest.json        # {format_version, exported_at, project:{title,description,icon}}
  data.json            # 全部结构化数据（含文件相对路径）
  files/<docid>_<名>   # 章节原文件
  books/<名>           # 整书原文件（多章共享，去重）
  audio/<scriptid>.mp3 # 播客音频（如有）
"""
import io
import json
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import (
    Project, Document, Chunk, KnowledgePoint, Question, QuizRecord,
    Flashcard, Annotation, DocSummary, PodcastScript,
)

EXPORT_FORMAT_VERSION = 1
LOCAL_USER = "local_user"

# ---------------------------------------------------------------- 导出

async def export_project(db: AsyncSession, project_id: str) -> bytes:
    p = await db.get(Project, project_id)
    if not p:
        raise ValueError("项目不存在")
    docs = (await db.execute(
        select(Document).where(Document.project_id == project_id)
        .order_by(Document.sort_order, Document.created_at)
    )).scalars().all()
    doc_ids = [d.id for d in docs]

    chunks = await _group(db, Chunk, Chunk.document_id, doc_ids, "seq")
    knowledge = await _group(db, KnowledgePoint, KnowledgePoint.document_id, doc_ids, "order_index")
    questions = await _group(db, Question, Question.document_id, doc_ids, "created_at")
    flashcards = await _group(db, Flashcard, Flashcard.document_id, doc_ids, "created_at")
    summaries = await _group(db, DocSummary, DocSummary.document_id, doc_ids, "updated_at")
    annotations = await _group(db, Annotation, Annotation.document_id, doc_ids, "created_at")
    podcasts = await _group(db, PodcastScript, PodcastScript.document_id, doc_ids, "updated_at")

    # 答题记录按题目归属
    q_ids = [q["id"] for rows in questions.values() for q in rows]
    quiz_records = {}
    if q_ids:
        for r in (await db.execute(select(QuizRecord).where(QuizRecord.question_id.in_(q_ids)))).scalars().all():
            quiz_records.setdefault(r.question_id, []).append(_row(r))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        doc_list = []
        for d in docs:
            dd = _row(d)
            # 章节原文件（阅读/学习内容）必须带上
            if d.file_path and Path(d.file_path).exists():
                rel = f"files/{d.id}_{Path(d.file_path).name}"
                z.writestr(rel, Path(d.file_path).read_bytes())
                dd["file_rel"] = rel
            # 整书原文件（book_file_path）与章节内容重复、体积大，导出时跳过；
            # 导入后章节仍可阅读，但「调节章节范围/预览整书」不可用（page_start/page_end 保留）
            doc_list.append(dd)

        # 播客音频
        for rows in podcasts.values():
            for s in rows:
                if s.get("audio_path") and Path(s["audio_path"]).exists():
                    rel = f"audio/{s['id']}.mp3"
                    z.writestr(rel, Path(s["audio_path"]).read_bytes())
                    s["audio_rel"] = rel

        z.writestr("data.json", json.dumps({
            "documents": doc_list,
            "chunks": chunks, "knowledge": knowledge, "questions": questions,
            "flashcards": flashcards, "summaries": summaries, "annotations": annotations,
            "podcasts": podcasts, "quiz_records": quiz_records,
        }, ensure_ascii=False, default=str))
        z.writestr("manifest.json", json.dumps({
            "format_version": EXPORT_FORMAT_VERSION,
            "exported_at": datetime.now().isoformat(),
            "project": {"title": p.title, "description": p.description, "icon": p.icon},
        }, ensure_ascii=False))
    return buf.getvalue()


async def _group(db: AsyncSession, model, doc_col, doc_ids: list[str], order_col) -> dict[str, list[dict]]:
    """按 document_id 分组导出模型行。"""
    if not doc_ids:
        return {}
    rows = (await db.execute(
        select(model).where(doc_col.in_(doc_ids)).order_by(order_col)
    )).scalars().all()
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(getattr(r, doc_col.key), []).append(_row(r))
    return out


def _row(obj) -> dict:
    """ORM 行 → 纯 dict（排除 SQLAlchemy 内部属性）。"""
    from sqlalchemy import inspect
    return {c.key: getattr(obj, c.key) for c in inspect(obj).mapper.column_attrs}


# ---------------------------------------------------------------- 导入

async def import_project(db: AsyncSession, content: bytes, title_override: str | None = None,
                         owner_id: str = LOCAL_USER) -> Project:
    """导入 .yqp 内容，重建项目，归属 owner_id。返回新项目。"""
    try:
        z = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise ValueError("文件不是有效的 .yqp 项目包")

    try:
        manifest = json.loads(z.read("manifest.json"))
        data = json.loads(z.read("data.json"))
    except (KeyError, json.JSONDecodeError) as e:
        raise ValueError(f"项目包格式无效：{e}")

    fmt = manifest.get("format_version", 0)
    if fmt != EXPORT_FORMAT_VERSION:
        raise ValueError(f"项目包版本不支持：{fmt}（当前支持 {EXPORT_FORMAT_VERSION}）")

    p_meta = manifest.get("project", {})
    proj = Project(
        user_id=owner_id,
        title=(title_override or p_meta.get("title") or "导入项目")[:128],
        description=p_meta.get("description", "") or "",
        icon=p_meta.get("icon", "") or "📦",
    )
    db.add(proj)
    await db.flush()

    save_dir = Path(settings.document_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    # 文档（生成新 id，重映射 parent_id / 文件）
    doc_id_map: dict[str, str] = {}
    for dd in data.get("documents", []):
        new_id = str(uuid.uuid4())
        doc_id_map[dd["id"]] = new_id

        file_path = ""
        if dd.get("file_rel"):
            try:
                raw = z.read(dd["file_rel"])
                ext = Path(dd.get("filename") or "f").suffix or ".bin"
                fp = save_dir / f"{new_id}_import{ext}"
                fp.write_bytes(raw)
                file_path = str(fp)
            except KeyError:
                pass
        book_path = ""
        if dd.get("book_rel"):
            try:
                raw = z.read(dd["book_rel"])
                bp = save_dir / f"book_{new_id[:8]}_{Path(dd['book_rel']).name}"
                bp.write_bytes(raw)
                book_path = str(bp)
            except KeyError:
                pass

        doc = Document(
            id=new_id, user_id=owner_id,
            title=dd.get("title") or "", filename=dd.get("filename") or "",
            file_path=file_path, content_type=dd.get("content_type") or "txt",
            chunk_count=0, project_id=proj.id,
            chapter_title=dd.get("chapter_title"),
            parent_id=doc_id_map.get(dd.get("parent_id")),
            sort_order=dd.get("sort_order") or 0,
            book_file_path=book_path or None,
            page_start=dd.get("page_start"), page_end=dd.get("page_end"),
        )
        db.add(doc)
    await db.flush()

    # 各内容表（document_id / 外键重映射）
    for doc_id, rows in data.get("chunks", {}).items():
        for r in rows:
            db.add(Chunk(document_id=doc_id_map[doc_id], seq=r.get("seq") or 0,
                         content=r.get("content") or "", heading=r.get("heading") or ""))
    kp_map: dict[str, str] = {}
    for doc_id, rows in data.get("knowledge", {}).items():
        for r in rows:
            new_kp = str(uuid.uuid4())
            kp_map[r["id"]] = new_kp
            db.add(KnowledgePoint(id=new_kp, document_id=doc_id_map[doc_id],
                                  parent_id=r.get("parent_id"),
                                  title=r.get("title") or "", summary=r.get("summary") or "",
                                  order_index=r.get("order_index") or 0))
    await db.flush()
    # 修正知识树 parent_id（旧 id → 新 id）
    for doc_id, rows in data.get("knowledge", {}).items():
        for r in rows:
            if r.get("parent_id") and r["parent_id"] in kp_map:
                kp = await db.get(KnowledgePoint, kp_map[r["id"]])
                if kp:
                    kp.parent_id = kp_map[r["parent_id"]]
    q_id_map: dict[str, str] = {}
    for doc_id, rows in data.get("questions", {}).items():
        for r in rows:
            new_qid = str(uuid.uuid4())
            q_id_map[r["id"]] = new_qid
            db.add(Question(id=new_qid, document_id=doc_id_map[doc_id],
                            qtype=r.get("qtype") or "choice",
                            question=r.get("question") or "", options=r.get("options") or "[]",
                            answer=r.get("answer") or "", explanation=r.get("explanation") or "",
                            source_text=r.get("source_text") or "",
                            discarded=bool(r.get("discarded")),
                            in_mistake_book=bool(r.get("in_mistake_book"))))
    for qid, rows in data.get("quiz_records", {}).items():
        if qid in q_id_map:
            for r in rows:
                db.add(QuizRecord(question_id=q_id_map[qid], user_answer=r.get("user_answer") or "",
                                  correct=bool(r.get("correct"))))
    for doc_id, rows in data.get("flashcards", {}).items():
        for r in rows:
            db.add(Flashcard(document_id=doc_id_map[doc_id], front=r.get("front") or "",
                             back=r.get("back") or "", visual=r.get("visual") or "",
                             status=r.get("status") or "new",
                             due_at=_parse_dt(r.get("due_at")),
                             stability=r.get("stability") or 0.0,
                             difficulty=r.get("difficulty") or 0.0,
                             reps=r.get("reps") or 0, lapses=r.get("lapses") or 0,
                             discarded=bool(r.get("discarded"))))
    for doc_id, rows in data.get("summaries", {}).items():
        for r in rows:
            db.add(DocSummary(document_id=doc_id_map[doc_id], scope=r.get("scope") or "overall",
                              unit_index=r.get("unit_index"), content=r.get("content") or "",
                              status=r.get("status") or "done", error=r.get("error") or ""))
    for doc_id, rows in data.get("annotations", {}).items():
        for r in rows:
            db.add(Annotation(document_id=doc_id_map[doc_id], unit_type=r.get("unit_type") or "chunk",
                              unit_index=r.get("unit_index") or 0,
                              start_offset=r.get("start_offset") or 0, end_offset=r.get("end_offset") or 0,
                              selected_text=r.get("selected_text") or "", content=r.get("content") or ""))
    for doc_id, rows in data.get("podcasts", {}).items():
        for r in rows:
            audio_path = ""
            if r.get("audio_rel"):
                try:
                    raw = z.read(r["audio_rel"])
                    ap = save_dir / f"podcast_{r['id']}.mp3"
                    ap.write_bytes(raw)
                    audio_path = str(ap)
                except KeyError:
                    pass
            db.add(PodcastScript(document_id=doc_id_map[doc_id], unit_index=r.get("unit_index") or 0,
                                 content=r.get("content") or "", audio_path=audio_path or None,
                                 status=r.get("status") or "done", error=r.get("error") or "",
                                 prev_content=r.get("prev_content"),
                                 audio_seconds=r.get("audio_seconds")))
    await db.commit()
    await db.refresh(proj)
    return proj


def _parse_dt(v):
    if not v:
        return None
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
