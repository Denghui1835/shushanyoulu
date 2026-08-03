"""关键词挖空背诵（纯死记风格）。

对一个阅读单元：LLM 提取值得死记的关键词（人名/概念/术语/数字/日期等），
在原文中定位所有出现位置，前端把关键词替换为「点击显示/隐藏」的空白。

LLM 只调用一次，结果缓存到 blank_caches 表；重复查看不再调模型。
"""
import json
import logging
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.api_scheduler import api_client
from app.core.api_scheduler.adapters.base import AdapterConfig
from app.core.reading_content import get_reading_units
from app.models import Document, BlankCache

logger = logging.getLogger("yuanqi.blank")

_MAX_UNIT_CHARS = 6000
_MAX_KEYWORDS = 15


async def get_blank_content(db: AsyncSession, document: Document, unit_index: int) -> dict:
    """返回某单元的关键词挖空内容：{title, text, blanks:[{keyword, positions:[{start,end}]}]}。"""
    units = await get_reading_units(db, document)
    if not (0 <= unit_index < len(units)):
        raise ValueError("单元不存在")
    unit = units[unit_index]
    text = unit["text"]

    keywords = await _get_keywords(db, document, unit_index, unit["title"], text)

    blanks = []
    for kw in keywords:
        pos = _find_all(text, kw)
        if pos:
            blanks.append({"keyword": kw, "positions": pos})
    return {"title": unit["title"], "text": text, "blanks": blanks}


async def _get_keywords(db: AsyncSession, document: Document, unit_index: int,
                        unit_title: str, text: str) -> list[str]:
    """取关键词：命中缓存直接返回；否则 LLM 提取并缓存。"""
    cached = (await db.execute(select(BlankCache).where(
        BlankCache.document_id == document.id, BlankCache.unit_index == unit_index
    ))).scalars().first()
    if cached and cached.keywords:
        try:
            return json.loads(cached.keywords)
        except json.JSONDecodeError:
            pass

    src = text[: _MAX_UNIT_CHARS]
    prompt = f"""从下面资料中提取适合「挖空背诵」的关键词——就是最值得死记硬背的词：
人名、专有名词、核心概念、关键术语、数字、日期、重要短语等。

资料《{document.title}》「{unit_title}」：
{src}

输出 JSON 数组（不要多余文字），如 ["电报","逻辑的起点","1876年"]。
要求：每个词 2-20 字，必须原样出现在资料原文中，共 6-15 个，按重要性排序。"""
    adapter = api_client.get_adapter(settings.default_model)
    resp = await adapter.chat_completion(
        [{"role": "user", "content": prompt}],
        AdapterConfig(temperature=0.3, max_tokens=1000, timeout=settings.request_timeout),
    )
    keywords = _parse_array(resp.content)

    # 过滤：必须在原文出现、去重、限数量
    seen: list[str] = []
    for kw in keywords:
        k = str(kw).strip()
        if 2 <= len(k) <= 20 and k in text and k not in seen:
            seen.append(k)
        if len(seen) >= _MAX_KEYWORDS:
            break

    # 缓存（即使为空也缓存，避免反复调模型）
    if cached:
        cached.keywords = json.dumps(seen, ensure_ascii=False)
    else:
        db.add(BlankCache(document_id=document.id, unit_index=unit_index,
                          keywords=json.dumps(seen, ensure_ascii=False)))
    await db.commit()
    logger.info("挖空关键词: doc=%s unit=%s (%d 个)", document.id, unit_index, len(seen))
    return seen


def _find_all(text: str, keyword: str) -> list[dict]:
    """返回 keyword 在 text 中所有出现位置的 [{start, end}]（不重叠，跳过已在覆盖区的）。"""
    positions: list[dict] = []
    start = 0
    while True:
        i = text.find(keyword, start)
        if i == -1:
            break
        positions.append({"start": i, "end": i + len(keyword)})
        start = i + len(keyword)  # 不重叠
    return positions


def _parse_array(text: str) -> list[str]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return []
