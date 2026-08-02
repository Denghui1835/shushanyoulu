"""文档总结生成：整体总结 + 页/块级总结。

- 模型：复用 api_client 默认配置（DeepSeek deepseek-chat，见 backend/.env）
- 超时：适配层 AdapterConfig.timeout（默认 settings.request_timeout）
- 降级：任何异常（网络/超时/解析）→ DocSummary.status='error' + error 文案，
  前端展示错误提示而非空白。
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.api_scheduler import api_client
from app.core.api_scheduler.adapters.base import AdapterConfig
from app.core.reading_content import get_reading_units
from app.models import Document, DocSummary

logger = logging.getLogger("yuanqi.summarize")

_MAX_SRC_CHARS = 9000  # 约 6000 tokens，超长截断


async def generate_summary(
    db: AsyncSession,
    document: Document,
    scope: str = "overall",
    unit_index: int | None = None,
) -> DocSummary:
    """生成并持久化一条总结。scope='overall' 或 'page'。

    已有同 scope+unit 记录时先删除再重建（幂等可重跑）。
    若内容超长会截断；异常会落 status='error'，绝不抛给前端。
    """
    # 清理旧记录
    old = await _find_summary(db, document.id, scope, unit_index)
    if old:
        await db.delete(old)
        await db.commit()

    summary = DocSummary(document_id=document.id, scope=scope,
                         unit_index=unit_index, status="generating")
    db.add(summary)
    await db.commit()
    await db.refresh(summary)

    try:
        src_text, unit_title = await _collect_source(db, document, scope, unit_index)
        if not src_text.strip():
            raise ValueError("没有可总结的内容")
        prompt = _build_prompt(document.title, src_text, unit_title, scope)
        adapter = api_client.get_adapter(settings.default_model)
        resp = await adapter.chat_completion(
            [{"role": "user", "content": prompt}],
            AdapterConfig(temperature=0.4, max_tokens=800, timeout=settings.request_timeout),
        )
        content = resp.content.strip()
        if not content:
            raise ValueError("模型返回为空")
        summary.content = content
        summary.status = "done"
        logger.info("Summary %s done: doc=%s unit=%s", scope, document.id, unit_index)
    except Exception as e:
        logger.warning("Summary %s failed for doc %s: %s", scope, document.id, e)
        summary.status = "error"
        summary.error = f"总结生成失败：{str(e)[:200]}"

    await db.commit()
    await db.refresh(summary)
    return summary


async def _find_summary(db: AsyncSession, document_id: str, scope: str, unit_index: int | None) -> DocSummary | None:
    stmt = select(DocSummary).where(
        DocSummary.document_id == document_id, DocSummary.scope == scope
    )
    if unit_index is not None:
        stmt = stmt.where(DocSummary.unit_index == unit_index)
    return (await db.execute(stmt)).scalars().first()


async def _collect_source(db: AsyncSession, document: Document, scope: str, unit_index: int | None) -> tuple[str, str]:
    """返回 (源文本, 单元标题)。整体总结拼接所有单元；页级取单个单元。"""
    units = await get_reading_units(db, document)
    if not units:
        return "", ""

    if scope == "page":
        if unit_index is None or not (0 <= unit_index < len(units)):
            raise ValueError(f"单元序号无效：{unit_index}")
        u = units[unit_index]
        return u["text"][: _MAX_SRC_CHARS], u["title"]
    else:
        # overall / story / concept —— 整章全文作为源
        parts = []
        for u in units:
            parts.append(f"【{u['title']}】\n{u['text']}")
        src = "\n\n".join(parts)
        if len(src) > _MAX_SRC_CHARS:
            src = src[: _MAX_SRC_CHARS] + "\n……（内容过长已截断）"
        return src, "整体"


def _build_prompt(doc_title: str, src: str, unit_title: str, scope: str) -> str:
    if scope == "story":
        return f"""请把学习资料《{doc_title}》讲成一段「听书式」总结，像给朋友讲一个连贯的故事。

要求：
- 口语化、连贯流畅，使用自然的过渡衔接语（如「接着我们来看…」「说到这儿…」）
- 按内容分段，每段前加一个小标题
- 覆盖本章核心知识点，适合戴耳机「听书」复习
- 全文 300-500 字

资料内容：
{src}"""
    if scope == "concept":
        return f"""请提炼学习资料《{doc_title}》的「核心概念要点」。

要求：
- 以概念条目形式列出（每条：概念名 —— 一句话定义 —— 一句关键解释/易错点）
- 覆盖本章最重要的概念，适合考前快速过一遍
- 8-15 条

资料内容：
{src}"""
    if scope == "overall":
        return f"""请对学习资料《{doc_title}》生成一段整体总结。
要求：150-250 字，覆盖核心主题与主要知识点结构，用清晰的小标题组织；面向复习者，突出重点与易错点。

资料内容：
{src}"""
    else:
        return f"""请对以下资料中的「{unit_title}」部分生成一段简洁总结。
要求：80-150 字，概括本部分的核心知识点，语言精炼，适合快速复习。

资料《{doc_title}》片段：
{src}"""
