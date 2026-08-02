"""Lightweight document parsing + chunking for 元气搭子.

Supports PDF (PyMuPDF), Word (python-docx), Markdown/TXT. Extracts text with
heading hints, then splits into token-budgeted chunks for LLM generation.
"""
import math
import re
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger("yuanqi.parsing")

try:
    import tiktoken
    _ENC = tiktoken.get_encoding("cl100k_base")
except Exception:  # pragma: no cover
    _ENC = None


def estimate_tokens(text: str) -> int:
    """Token estimate for mixed Chinese/English text."""
    if _ENC is not None:
        try:
            return len(_ENC.encode(text))
        except Exception:
            pass
    # fallback: ~1.5 chars/token is a rough Chinese/English blend
    return max(1, math.ceil(len(text) / 1.5))


_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)$")


def _extract_heading(line: str) -> tuple[str, int] | None:
    """If the line looks like a markdown heading, return (title, level)."""
    m = _HEADING_RE.match(line.strip())
    if m:
        return m.group(2).strip(), len(m.group(1))
    return None


def parse_file(path: Path) -> tuple[str, list[dict]]:
    """Parse a file into (plain_text, heading_hints).

    heading_hints: list of {"title", "level", "offset_char"} where offset_char
    points into plain_text. Used to attach section headings to chunks.
    """
    ext = path.suffix.lower()
    text = ""
    hints: list[dict] = []

    if ext == ".pdf":
        import fitz  # PyMuPDF
        doc = fitz.open(str(path))
        pages = []
        for pno in range(doc.page_count):
            page = doc.load_page(pno)
            pages.append(page.get_text("text"))
        doc.close()
        text = "\n\n".join(pages)
        # rough heading hints from lines that look short & end with punctuation-less
        _scan_headings(text, hints, max_level=2)

    elif ext == ".docx":
        import docx
        d = docx.Document(str(path))
        parts = []
        for para in d.paragraphs:
            style = (para.style.name or "").lower() if para.style else ""
            if not para.text.strip():
                continue
            if "heading" in style or "title" in style:
                level = 1 if "title" in style else (2 if "heading 2" in style else 1)
                hints.append({"title": para.text.strip(), "level": level,
                              "offset_char": _joined_len(parts)})
                parts.append(f"\n## {para.text.strip()}\n")
            else:
                parts.append(para.text)
        text = "\n".join(parts)

    elif ext in (".md", ".markdown", ".txt", ".text"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        _scan_headings(text, hints, max_level=4)

    elif ext == ".pptx":
        from pptx import Presentation
        prs = Presentation(str(path))
        parts = []
        for slide in prs.slides:
            for shape in slide.shapes:
                if shape.has_text_frame:
                    t = shape.text_frame.text.strip()
                    if t:
                        parts.append(t)
        text = "\n\n".join(parts)

    else:
        raise ValueError(f"不支持的文档类型: {ext}")

    return text, hints


def _joined_len(parts: list[str]) -> int:
    return sum(len(p) for p in parts)


def _scan_headings(text: str, hints: list[dict], max_level: int) -> None:
    """Very cheap heuristic: markdown-style lines and short standalone lines."""
    offset = 0
    for line in text.splitlines():
        raw = line.strip()
        hl = _extract_heading(line)
        if hl:
            title, level = hl
            if level <= max_level:
                hints.append({"title": title, "level": level, "offset_char": offset})
        offset += len(line) + 1  # + newline


def chunk_text(text: str, hints: list[dict] | None = None,
               chunk_tokens: int | None = None) -> list[dict]:
    """Split text into chunks sized by token budget.

    Hints (section headings) are respected as chunk boundaries when possible.
    Returns list of {"content", "heading"}.
    """
    chunk_tokens = chunk_tokens or settings.chunk_size_tokens
    hints = hints or []
    hint_map = {h["offset_char"]: h["title"] for h in hints}

    # First split by headings into sections
    sections: list[dict] = []  # {"heading", "text"}
    boundaries = sorted(hint_map.keys())
    if not boundaries:
        sections.append({"heading": "", "text": text})
    else:
        for i, off in enumerate(boundaries):
            seg_text = text[off:(boundaries[i + 1] if i + 1 < len(boundaries) else len(text))]
            seg_text = seg_text.strip()
            if seg_text:
                sections.append({"heading": hint_map[off], "text": seg_text})

    # Then split each section into token-budgeted chunks
    chunks: list[dict] = []
    for sec in sections:
        sec_text = sec["text"]
        while estimate_tokens(sec_text) > chunk_tokens:
            # find a sentence break near budget
            cut = _find_cut(sec_text, chunk_tokens)
            piece, sec_text = sec_text[:cut], sec_text[cut:]
            if piece.strip():
                chunks.append({"content": piece.strip(), "heading": sec["heading"]})
        if sec_text.strip():
            chunks.append({"content": sec_text.strip(), "heading": sec["heading"]})

    # If nothing produced (empty doc), keep one empty-ish chunk
    if not chunks:
        chunks.append({"content": text.strip() or "(空文档)", "heading": ""})

    logger.info("Chunked %d chars -> %d chunks", len(text), len(chunks))
    return chunks


def _find_cut(text: str, chunk_tokens: int) -> int:
    """Find a good cut position near the token budget."""
    budget = min(len(text), int(chunk_tokens * 1.5))
    window = text[:budget]
    # prefer last sentence-ending punctuation within the window
    for marker in ("。", "！", "？", "？", ". ", "!\n", "?\n", "\n\n"):
        idx = window.rfind(marker)
        if idx != -1 and idx > budget * 0.5:
            return idx + len(marker) if not marker.endswith("\n") else idx + 1
    return budget
