"""阅读单元解析：把文档组织成「可阅读、可批注、可总结、可朗读」的单元序列。

单元定义：
- PDF：以实际 PDF 页面为单位（unit_type='page'），从磁盘文件按页取文本。
- 非 PDF（Word/Markdown/TXT/PPT）：以数据库 Chunk 为单位（unit_type='chunk'，
  对应章节标题 + token 预算分块）。

单元序号的稳定性：
- PDF 页号天然稳定；
- 非 PDF 的 chunk.seq 在文档不重新解析时稳定，批注定位依赖这一点。
"""
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, Chunk
from app.core.paths import resolve_doc_file

logger = logging.getLogger("yuanqi.reading")


async def get_reading_units(db: AsyncSession, document: Document) -> list[dict]:
    """返回文档的阅读单元列表。

    每项: {"index": int, "unit_type": "page"|"chunk",
           "title": str, "text": str}
    """
    content_type = (document.content_type or "").lower()

    if content_type == "pdf":
        return _pdf_pages(document)
    else:
        return await _chunk_units(db, document)


def _pdf_pages(document: Document) -> list[dict]:
    """PDF：逐页提取文本，每页一个单元。"""
    # 路径兜底解析：库里的绝对路径可能因项目改名/搬迁而失效（见 core/paths.py）
    path = resolve_doc_file(document.file_path)
    if path is None:
        return []

    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.warning("PyMuPDF 未安装，无法解析 PDF 阅读单元")
        return []

    units: list[dict] = []
    # 若有整书引用（page_start），页码用书内物理页编号，保证边界共享页在各章显示一致
    base = document.page_start if document.page_start is not None else 0
    try:
        doc = fitz.open(str(path))
        for pno in range(doc.page_count):
            page = doc.load_page(pno)
            text = page.get_text("text").strip()
            units.append({
                "index": pno,
                "unit_type": "page",
                "title": f"第 {base + pno + 1} 页",
                "text": text or "(本页无文本)",
            })
        doc.close()
    except Exception as e:
        logger.warning("PDF 阅读单元解析失败: %s", e)
        return []
    return units


async def _chunk_units(db: AsyncSession, document: Document) -> list[dict]:
    """非 PDF：数据库 Chunk 按 seq 组织为单元。"""
    chunks = (await db.execute(
        select(Chunk).where(Chunk.document_id == document.id).order_by(Chunk.seq)
    )).scalars().all()

    units: list[dict] = []
    for c in chunks:
        title = c.heading or f"第 {c.seq + 1} 节"
        units.append({
            "index": c.seq,
            "unit_type": "chunk",
            "title": title,
            "text": c.content,
        })
    if not units:
        logger.warning("文档 %s 无 chunk，阅读单元为空", document.id)
    return units
