"""知识树生成."""
import json
import logging
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.api_scheduler import api_client
from app.core.api_scheduler.adapters.base import AdapterConfig
from app.core.parsing import estimate_tokens
from app.models import Document, Chunk, KnowledgePoint

logger = logging.getLogger("yuanqi.knowledge")


async def generate_knowledge_tree(db: AsyncSession, document_id: str) -> list[KnowledgePoint]:
    """Generate a knowledge tree for a document (LLM). Returns root-level nodes."""
    doc = await db.get(Document, document_id)
    if not doc:
        raise ValueError("文档不存在")
    chunks = (await db.execute(
        select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.seq)
    )).scalars().all()
    if not chunks:
        raise ValueError("文档尚未分块")

    src = "\n\n".join(c.content for c in chunks)
    while estimate_tokens(src) > 7000 and len(src) > 3000:
        src = src[:int(len(src) * 0.8)]

    prompt = f"""阅读下面的学习资料《{doc.title}》，生成它的知识结构树。

资料节选：
{src}

输出 JSON 对象（不要多余文字）：
{{"nodes": [
  {{"title": "一级主题", "children": [{{"title": "二级主题", "summary": "一句话概括"}}]}}
]}}
要求：
- 3-6 个一级主题，每个主题 2-5 个子节点
- title 简洁（≤12字），summary 每个子节点一句话（≤40字）"""

    adapter = api_client.get_adapter(settings.default_model)
    resp = await adapter.chat_completion(
        [{"role": "user", "content": prompt}],
        AdapterConfig(temperature=0.4, max_tokens=2500),
    )
    data = _parse_obj(resp.content)

    # clear existing tree for this doc (regenerate)
    old = (await db.execute(
        select(KnowledgePoint).where(KnowledgePoint.document_id == document_id)
    )).scalars().all()
    for o in old:
        await db.delete(o)
    await db.flush()

    points: list[KnowledgePoint] = []
    order = 0
    for top in data.get("nodes", []):
        top_title = str(top.get("title", "")).strip()
        if not top_title:
            continue
        parent = KnowledgePoint(
            document_id=doc.id, parent_id=None, title=top_title,
            summary=str(top.get("summary", "")), order_index=order,
        )
        db.add(parent)
        await db.flush()
        order += 1
        points.append(parent)
        for sub in top.get("children", []):
            child = KnowledgePoint(
                document_id=doc.id, parent_id=parent.id,
                title=str(sub.get("title", "")).strip(),
                summary=str(sub.get("summary", "")),
                order_index=order,
            )
            db.add(child)
            await db.flush()
            order += 1
            points.append(child)

    await db.commit()
    logger.info("Knowledge tree: %d nodes for doc %s", len(points), document_id)
    return points


def _parse_obj(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return {"nodes": []}
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return {"nodes": []}
