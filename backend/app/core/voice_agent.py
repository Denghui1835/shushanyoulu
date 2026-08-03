# -*- coding: utf-8 -*-
"""语音助手：对话 + 解析并提议章节目录修改。

设计：LLM 在回复末尾附一个 <<<EDIT>>> 标记的 JSON 块（operations 列表），
后端解析后把它解析为「完整的新章节列表（供 /chapters/sync 使用）+ 人类可读的变更描述」。
前端展示变更，由用户选择「应用」或「弃用」（弃用即不调用 sync，什么都不改）。

支持操作：rename / delete / add / merge。
不支持原生 function-calling 的适配层也能工作，复用 TOC 提取的「LLM 输出 JSON」模式。
"""
import json
import logging
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.api_scheduler import api_client
from app.core.api_scheduler.adapters.base import AdapterConfig
from app.models import Document, Project

logger = logging.getLogger("yuanqi.voice_agent")

_EDIT_RE = re.compile(r"<<<EDIT>>>\s*([\s\S]*?)\s*<<<END>>>")
_MAX_HISTORY = 8

_OP_DESC = {
    "rename": "改名", "delete": "删除", "add": "新增", "merge": "合并",
}

_SYSTEM_TEMPLATE = """你是「小书虫」里的语音助手，正在帮用户管理一本书《{title}》的章节目录。
你可以和用户闲聊、解答学习问题，也可以按用户要求修改章节目录。

当前章节列表（chapter 字段必须原样引用下列章节名）：
{chapters}

如果用户要求修改目录，请在回答的最后附上如下 JSON 块（块外不要出现其它代码/JSON）：
<<<EDIT>>>
{{"operations": [ ... ]}}
<<<END>>>

operations 每项是以下之一：
- {{"op": "rename", "chapter": "<列表中的原章节名>", "title": "<新标题>"}}
- {{"op": "delete", "chapter": "<列表中的原章节名>"}}
- {{"op": "add", "title": "<新章节名>", "page_start": <起始页>, "page_end": <结束页>}}
- {{"op": "merge", "chapters": ["<章节名1>", "<章节名2>", ...], "title": "<合并后标题>"}}

注意：
- chapter 字段要与列表中的章节名一致（若记不准可省略「第X章：」里的冒号后的部分，但尽量原样）。
- 只有用户明确要求修改时才输出 EDIT 块；普通聊天绝对不要输出。
- 回答用中文，简洁友好，先一句话说明你将做什么改动（或直接答疑）。"""


def build_agent_messages(project_title: str, chapters: list[dict], message: str,
                         history: list[dict]) -> list[dict[str, str]]:
    lines = []
    for i, ch in enumerate(chapters):
        pages = "—"
        if ch.get("page_start") is not None and ch.get("page_end") is not None:
            pages = f"第{ch['page_start'] + 1}-{ch['page_end'] + 1}页"
        name = ch.get("chapter_title") or ch.get("title") or "(未命名)"
        lines.append(f"{i + 1}. {name} —— {pages}")
    system = _SYSTEM_TEMPLATE.format(title=project_title, chapters="\n".join(lines))
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    for h in history[-_MAX_HISTORY:]:
        role = h.get("role") if h.get("role") in ("user", "assistant") else "user"
        messages.append({"role": role, "content": str(h.get("content", ""))})
    messages.append({"role": "user", "content": message})
    return messages


def _parse_operations(reply: str) -> list[dict]:
    m = _EDIT_RE.search(reply)
    if not m:
        return []
    raw = m.group(1).strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("解析章节修改块失败: %s", e)
        return []
    ops = data.get("operations") if isinstance(data, dict) else None
    return ops if isinstance(ops, list) else []


def _strip_edit_block(reply: str) -> str:
    return _EDIT_RE.sub("", reply).strip()


def resolve_operations(chapters: list[dict], ops: list[dict]) -> tuple[list[dict], list[dict], list[str]]:
    """把 LLM 操作解析为 (new_chapters 完整同步列表, 人类可读变更, warnings)。

    chapters 每项: {id, title, chapter_title, page_start, page_end, book_ref_document_id}
    """
    by_name: dict[str, dict] = {}
    for ch in chapters:
        name = (ch.get("chapter_title") or ch.get("title") or "").strip()
        if name:
            by_name[name] = ch

    def find(name: str):
        if not name:
            return None
        if name in by_name:
            return by_name[name]
        for n, ch in by_name.items():
            if name in n or n in name:
                return ch
        return None

    deleted: set[str] = set()
    renames: dict[str, str] = {}
    merge_target: dict[str, tuple[int, int, str]] = {}  # 保留的 doc_id -> (min_start, max_end, 新标题)
    adds: list[dict] = []
    ops_desc: list[dict] = []
    warnings: list[str] = []

    for op in ops:
        kind = op.get("op")
        try:
            if kind == "rename":
                ch = find(op.get("chapter"))
                new_title = (op.get("title") or "").strip()
                if not ch:
                    warnings.append(f"找不到章节「{op.get('chapter')}」，已忽略改名")
                elif not new_title:
                    warnings.append("改名为空，已忽略")
                else:
                    renames[ch["id"]] = new_title
                    ops_desc.append({"type": "rename", "chapter": ch.get("chapter_title") or ch.get("title"),
                                     "to": new_title})
            elif kind == "delete":
                ch = find(op.get("chapter"))
                if not ch:
                    warnings.append(f"找不到章节「{op.get('chapter')}」，已忽略删除")
                else:
                    deleted.add(ch["id"])
                    ops_desc.append({"type": "delete", "chapter": ch.get("chapter_title") or ch.get("title")})
            elif kind == "add":
                title = (op.get("title") or "").strip()
                ps, pe = op.get("page_start"), op.get("page_end")
                if not title:
                    warnings.append("新增章节标题为空，已忽略")
                elif not isinstance(ps, int) or not isinstance(pe, int) or ps < 1 or pe < ps:
                    warnings.append(f"新增章节「{title}」页码无效，已忽略")
                else:
                    adds.append({"title": title, "page_start": ps - 1, "page_end": pe - 1})
                    ops_desc.append({"type": "add", "title": title, "pages": f"{ps}-{pe}"})
            elif kind == "merge":
                found = [c for c in (find(n) for n in (op.get("chapters") or [])) if c]
                new_title = (op.get("title") or "").strip() or "合并章节"
                if len(found) < 2:
                    warnings.append("合并需要至少两个已定位的章节，已忽略")
                elif len({c.get("book_ref_document_id") for c in found}) > 1:
                    warnings.append("合并的章节来自不同整书，已忽略")
                else:
                    first, last = found[0], found[-1]
                    merge_target[first["id"]] = (first["page_start"], last["page_end"], new_title)
                    for c in found[1:]:
                        deleted.add(c["id"])
                    ops_desc.append({"type": "merge",
                                     "chapters": [c.get("chapter_title") or c.get("title") for c in found],
                                     "to": new_title})
            else:
                warnings.append(f"未知操作类型「{kind}」，已忽略")
        except Exception as e:  # noqa: BLE001
            logger.exception("解析操作失败 %s", op)
            warnings.append(f"操作「{op.get('op')}」解析出错：{e}")

    # 保持当前顺序构建完整同步列表
    new_chapters: list[dict] = []
    for ch in chapters:
        cid = ch["id"]
        if cid in deleted:
            continue
        title = renames.get(cid) or (ch.get("chapter_title") or ch.get("title"))
        row = {"document_id": cid, "title": title,
               "page_start": ch.get("page_start", 0), "page_end": ch.get("page_end", 0)}
        if cid in merge_target:
            _, max_end, mt = merge_target[cid]
            row["title"] = mt
            row["page_end"] = max_end
        new_chapters.append(row)

    # 新增章节：默认挂到第一个整书章节所属的书
    book_ref = next((c.get("book_ref_document_id") for c in chapters if c.get("book_ref_document_id")), None)
    for a in adds:
        new_chapters.append({"document_id": None, "title": a["title"],
                             "page_start": a["page_start"], "page_end": a["page_end"],
                             "source_document_id": book_ref})
    return new_chapters, ops_desc, warnings


async def run_agent_turn(db: AsyncSession, project_id: str, message: str,
                         history: list[dict]) -> dict:
    """执行一轮语音助手对话，返回 {reply, proposal|None}。"""
    project = await db.get(Project, project_id)
    if not project:
        raise ValueError("项目不存在")
    docs = (await db.execute(
        select(Document).where(Document.project_id == project_id)
        .order_by(Document.sort_order, Document.created_at)
    )).scalars().all()
    # 语音助手当前只管叶子章节，分组(部分/卷)节点暂不纳入（后续扩展）
    docs = [d for d in docs if d.content_type != "group"]

    # 每本整书取第一个章节作为该书参考章节 id（与 get_project 一致）
    ref_by_path: dict[str, str] = {}
    for d in docs:
        if d.book_file_path and d.book_file_path not in ref_by_path:
            ref_by_path[d.book_file_path] = d.id
    chapters = [{
        "id": d.id, "title": d.title, "chapter_title": d.chapter_title or "",
        "page_start": d.page_start, "page_end": d.page_end,
        "book_ref_document_id": ref_by_path.get(d.book_file_path),
    } for d in docs]

    messages = build_agent_messages(project.title, chapters, message, history)
    adapter = api_client.get_adapter(settings.default_model)
    resp = await adapter.chat_completion(
        messages, AdapterConfig(temperature=0.2, max_tokens=2000, timeout=settings.request_timeout),
    )
    reply = resp.content or ""
    ops = _parse_operations(reply)
    clean_reply = _strip_edit_block(reply)
    proposal = None
    if ops:
        new_chapters, ops_desc, warnings = resolve_operations(chapters, ops)
        if ops_desc:
            proposal = {"operations": ops_desc, "new_chapters": new_chapters, "warnings": warnings}
    return {"reply": clean_reply, "proposal": proposal}
