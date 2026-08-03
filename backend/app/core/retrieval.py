"""Lightweight retrieval for 书山有路.

MVP uses lexical retrieval (jieba tokenization + overlap scoring) over stored
chunks — no heavy embedding model needed. The interface is a simple function so a
vector backend can be swapped in later without touching callers.
"""
import logging
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, Chunk

logger = logging.getLogger("yuanqi.retrieval")

try:
    import jieba
    jieba.setLogLevel(logging.WARNING)
    _TOKENIZER = jieba.lcut
except Exception:  # pragma: no cover
    def _TOKENIZER(text: str) -> list[str]:
        # crude fallback: split on non-word chars
        import re
        return [t for t in re.split(r"[\s\W_]+", text) if len(t) > 1]


_STOPWORDS = {
    "的", "了", "是", "在", "和", "与", "及", "或", "一个", "我们", "你们",
    "他们", "这个", "那个", "可以", "进行", "对于", "以及", "这样", "一些",
    "这", "那", "之", "对", "把", "被", "让", "等", "中", "上", "下",
}


def _tokenize(text: str) -> list[str]:
    return [t for t in _TOKENIZER(text.lower()) if t.strip() and t not in _STOPWORDS and len(t.strip()) > 1]


def _score(query_tokens: list[str], chunk_text: str) -> float:
    ct = Counter(_tokenize(chunk_text))
    if not ct:
        return 0.0
    score = 0.0
    for q in query_tokens:
        if q in ct:
            # log-frequency weighting: rarer query terms matter more
            score += 1.0
    overlap = sum(1 for q in query_tokens if q in ct)
    # normalize by query size and give small boost to length match
    if not query_tokens:
        return 0.0
    score = overlap / len(query_tokens)
    # bonus if key terms appear multiple times
    return score + min(0.2, 0.05 * sum(1 for q in query_tokens if ct[q] >= 2))


async def retrieve(
    db: AsyncSession,
    query: str,
    document_id: str | None = None,
    top_k: int = 4,
    min_score: float = 0.15,
) -> list[dict]:
    """Return top-k relevant chunks for a query within a document (or all docs).

    Returns list of {"chunk_id", "content", "heading", "document_id", "title", "score"}.
    """
    q_tokens = _tokenize(query)
    if not q_tokens:
        return []

    stmt = select(Chunk)
    if document_id:
        stmt = stmt.where(Chunk.document_id == document_id)
    chunks = (await db.execute(stmt)).scalars().all()

    scored = []
    for c in chunks:
        s = _score(q_tokens, c.content)
        if s >= min_score:
            scored.append({"chunk_id": c.id, "content": c.content, "heading": c.heading,
                           "document_id": c.document_id, "score": s})
    scored.sort(key=lambda x: x["score"], reverse=True)

    # attach document titles
    doc_ids = {s["document_id"] for s in scored}
    if doc_ids:
        docs = (await db.execute(select(Document).where(Document.id.in_(doc_ids)))).scalars().all()
        title_map = {d.id: d.title for d in docs}
        for s in scored:
            s["title"] = title_map.get(s["document_id"], "")
    return scored[:top_k]
