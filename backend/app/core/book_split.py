"""整书 PDF 目录识别与自动分章。

流程：保存原书 → （可选）按页码范围提取文本 → 打分制找目录页 → LLM 提取「章→节」
→ 无目录页则 LLM 抽样归纳 → 印刷页码→物理页校准（优先标题匹配）→ 切成章节范围 →
每个章节写成子 PDF 并落库为独立 Document。

精度与容错：
- 目录页码→物理页换算为启发式近似，结果允许用户在项目详情页人工修正（改名/排序）。
- 输出经校验（≥2 章、页码升序、在书内）；退化结果（仅 1 章 / 最大章占比 >90%）
  由调用方判定并明确报错，不静默切错。
"""
import json
import logging
import re
from pathlib import Path

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.api_scheduler import api_client
from app.core.api_scheduler.adapters.base import AdapterConfig
from app.core.parsing import parse_file, chunk_text
from app.models import Document, Chunk

logger = logging.getLogger("yuanqi.book_split")

_MAX_TOC_CHARS = 5000
_MAX_SAMPLE_CHARS = 5000
_LOCAL_USER_ID = "local_user"


# ---------------------------------------------------------------- 页数与取文本

def count_pdf_pages(pdf_path: str | Path) -> int:
    """返回 PDF 总页数。"""
    import fitz
    doc = fitz.open(str(pdf_path))
    n = doc.page_count
    doc.close()
    return n


def extract_page_texts(pdf_path: str | Path, start_page: int = 1, end_page: int | None = None) -> list[str]:
    """按页码范围（1 基）提取文本；返回该范围内的逐页文本（相对范围）。"""
    import fitz
    doc = fitz.open(str(pdf_path))
    total = doc.page_count
    start = max(0, start_page - 1)
    end = min(total - 1, (end_page or total) - 1)
    texts: list[str] = []
    for pno in range(start, end + 1):
        texts.append(doc.load_page(pno).get_text("text"))
    doc.close()
    return texts


# ---------------------------------------------------------------- 目录页识别（打分制）

_TOC_LINE_RE = re.compile(r"^(.{4,50}?)[.．·…\s]{2,}(\d{1,4})\s*$")


def _toc_line_info(line: str) -> tuple[str, int] | None:
    m = _TOC_LINE_RE.match(line.strip())
    if m:
        return m.group(1).strip(), int(m.group(2))
    return None


def _score_toc_page(page_text: str, total_pages: int) -> int:
    """给一页打分：目录标题 + 目录式行数量 + 页码升序 + 页码在书内。"""
    lines = [l.strip() for l in page_text.splitlines() if l.strip()]
    score = 0
    # 目录标题
    head = [l for l in lines[:4] if l]
    if any("目录" in l and len(l) <= 10 for l in head) or any("Contents" in l for l in head):
        score += 3
    # 目录式行
    infos = [t for t in (_toc_line_info(l) for l in lines) if t]
    score += min(3, len(infos) // 3)
    nums = [n for _, n in infos]
    if len(nums) >= 2:
        if all(nums[i] < nums[i + 1] for i in range(len(nums) - 1)):
            score += 1
        if all(0 < n <= max(1, total_pages) for n in nums):
            score += 1
    return score


def find_toc_pages(text_pages: list[str], total_pages: int, max_scan: int = 30) -> list[int]:
    """打分制找目录页：返回范围内最像目录的物理页（相对范围下标），按分数降序。"""
    scored = [(i, _score_toc_page(text, total_pages)) for i, text in enumerate(text_pages[:max_scan])]
    scored.sort(key=lambda x: -x[1])
    # 至少要有目录标题（≥3）才认定是目录页；只取最强候选
    hits = [i for i, s in scored if s >= 4]
    return hits


# ---------------------------------------------------------------- LLM 目录提取/归纳

def _toc_schema_hint() -> str:
    return """输出 JSON 数组（不要任何多余文字），每项：
{"level": 1, "title": "部分/卷标题", "page_number": 页码}
- level 1 = 部分/卷/编（分卷分组标题）；level 2 = 章
- 有分卷/部分的书：先输出各部分（level 1），再输出各部分下的章（level 2）
- 没有分卷的书：所有条目都标 level 2
- 卷/部分与其第一个章节常在同一页（卷首即章首），同页也要都输出，绝不省略章
- 逐条列出目录中的每一个章/部分条目，不要合并、不要跳过、不要自作主张删减
- 只输出部分与章，不要输出节；只保留有页码的条目
- page_number 用目录中标注的页码，原样返回不要换算
- 前言/序/引言/导读/致读者、附录/参考文献/后记/致谢等正文前置或后置板块保留为 level 2
- 不要包含封面、版权页、目录本身"""


async def extract_toc_entries(toc_text: str, book_title: str, total_pages: int) -> list[dict]:
    """LLM 从目录页文本提取部分/章级目录；输出经校验，无效返回空列表。"""
    prompt = f"""以下是《{book_title}》的目录页文本（全书共 {total_pages} 页）。请提取它的部分与章级目录。

目录页文本：
{toc_text[:_MAX_TOC_CHARS]}

{_toc_schema_hint()}"""
    entries = await _llm_toc(prompt)
    return _validate_entries(entries, total_pages)


async def infer_toc_from_book(sample: str, book_title: str, total_pages: int) -> list[dict]:
    """无目录页兜底：LLM 依据抽样文本归纳章级目录。输出经校验。"""
    prompt = f"""以下是《{book_title}》（全书共 {total_pages} 页）的开头若干页与章节标题行的抽样文本。
这本书没有明显的目录页，请通读抽样内容，归纳出这本书的部分与章级目录。

抽样文本：
{sample[:_MAX_SAMPLE_CHARS]}

输出 JSON 数组，每项：
{{"level": 1, "title": "部分/卷标题", "page_number": 估计起始页码(1基)}} 或
{{"level": 2, "title": "章标题", "page_number": 估计起始页码(1基)}}
- 有分卷/部分的书：部分标 level 1，其下章标 level 2；没有分卷则全标 level 2"""
    entries = await _llm_toc(prompt)
    return _validate_entries(entries, total_pages)


def _validate_entries(entries: list[dict], total_pages: int) -> list[dict]:
    """校验：按标题判定部分/章两级，页码在书内、按(页码,层级)去重、按页码升序。

    卷/部分与其首个章节常同页（卷首=章首），必须按 (页码, 层级) 去重，否则章会被卷顶掉。
    """
    seen: set[tuple[int, int]] = set()
    cleaned: list[dict] = []
    for e in sorted(entries, key=lambda x: x.get("page_number", 0)):
        p = e.get("page_number", 0)
        lv = _entry_level(e)
        key = (p, lv)
        if 1 <= p <= max(1, total_pages) and key not in seen:
            seen.add(key)
            cleaned.append({"level": lv, "title": e["title"], "page_number": p})
    return cleaned


async def _llm_toc(prompt: str) -> list[dict]:
    adapter = api_client.get_adapter(settings.default_model)
    resp = await adapter.chat_completion(
        [{"role": "user", "content": prompt}],
        AdapterConfig(temperature=0.3, max_tokens=3000, timeout=settings.request_timeout),
    )
    return _parse_entries(resp.content)


# ---------------------------------------------------------------- 无目录页：全书扫描 + LLM 整理

# 前置内容标题（前言/序/引言/致读者等）；须后跟标点或行尾，避免误配「程序」「序列」等
_FRONT_TITLE_RE = re.compile(
    r"^(前言|序言|自序|序|引言|导言|导读|致读者|写在前面|开场白|卷首语)([\s：:．.。—\-、]|$)"
)

_CHAPTER_LOOSE_RE = re.compile(
    r"^(第[一二三四五六七八九十百千万0-9０-９]+[章节讲篇课部])(.{0,60})",
    re.I,
)
# 部分分隔：「第一部分：推理的起源」
_PART_RE = re.compile(r"^第[一二三四五六七八九十百千万0-9]+部分\s*[：:]?\s*(.{0,40})")
# 前置/后置章节：「前言/序/引言/致读者/结语/附录/后记/致谢/参考文献」
_FRONT_BACK_RE = re.compile(r"^(序言?|自序|引言|导言|导读|前言|致读者|致谢|后记|跋|结语|附录|参考文献)([A-Z0-9：:.\s]*)(.{0,30})")
# 英文章节：「Chapter 3」「Part II」「Section 1.1」
_EN_RE = re.compile(r"^(Chapter|Part|Section)\s+[0-9IVXLC]+[：:.\s]*(.{0,40})", re.I)
# 章节号后紧跟这些虚词/标点 → 是正文回顾句（如「第X章的…」「第X章说…」「第一章，我们聊…」）
_RECAP_NEXT = set("的了说讲结尾给留要正建做引把将从是有会能在后前这那，,。的着过")


def _is_chapter_candidate(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > 70:
        return False
    m = _CHAPTER_LOOSE_RE.match(s)
    if m:
        after = m.group(2)[:1]
        # 后跟回顾虚词 → 剔除；后跟冒号/空格/破折号或直接跟标题 → 保留
        return after not in _RECAP_NEXT
    if _PART_RE.match(s):
        return True
    if _EN_RE.match(s):
        return True
    fm = _FRONT_BACK_RE.match(s)
    if fm and len(s) <= 40:
        # 前置/后置标题须为短行（避免正文中「见附录」「结语见…」等提及）
        return True
    return False


def scan_chapter_headings(pdf_path: str | Path, total_pages: int,
                          start_page: int = 1, end_page: int | None = None) -> list[dict]:
    """在页码范围（1 基，默认全书）内扫描疑似章节标题行。

    宽松匹配「第X章」开头行，再确定性剔除回顾句（第X章后跟 的了说讲结尾 等虚词）。
    返回 [{page_index(0基, 全书物理页), row, line, first_line}]；交由 LLM 甄别真正的章节开篇。
    """
    import fitz
    start = max(0, start_page - 1)
    end = min(total_pages, end_page or total_pages) - 1
    doc = fitz.open(str(pdf_path))
    candidates: list[dict] = []
    for phys in range(start, end + 1):
        lines = [l.strip() for l in doc.load_page(phys).get_text("text").splitlines() if l.strip()]
        if not lines:
            continue
        first_line = lines[0][:30]
        # 扫描到页内较深位置：部分书把章节标题嵌在页中（如图文开篇/装饰标题）
        for idx, l in enumerate(lines[:40]):
            if _is_chapter_candidate(l) and len(l) <= 70:
                candidates.append({
                    "page_index": phys, "row": idx, "line": l[:70],
                    "first_line": first_line,
                })
                break  # 每页取最先命中的一行
    doc.close()
    logger.info("扫描到 %d 个章节标题候选（第 %d-%d 页）", len(candidates), start + 1, end + 1)
    return candidates


async def infer_toc_from_scan(candidates: list[dict], book_title: str, total_pages: int) -> list[dict]:
    """LLM 从全书扫描候选中整理出真正的部分/章级目录。

    返回 [{level, title, page_number}]，page_number 为物理页索引（0 基）；
    level 1=部分/卷（分组），2=章。
    """
    if not candidates:
        return []
    cand_text = json.dumps(candidates, ensure_ascii=False)
    prompt = f"""《{book_title}》（共 {total_pages} 页）没有可识别的目录页。
下面是从全书扫描出的「章节标题行」候选（正则已过滤掉多数回顾句），每项含物理页索引 page_index（0 基）、行位置 row、该行文本 line、该页首行 first_line：
{cand_text[:6000]}

请筛选出真正的「部分/卷」与「章」级开篇并整理成层级目录：
- 「第X部分/第X卷/第X编/上中下卷」等分卷标题 → level 1（分组）
- 每个真正的章节/板块开篇（该页以此标题开头、后续是该板块正文）→ level 2
- 也保留前置与后置板块作为章（level 2）：前言/序/引言/致读者、结语/后记/致谢/附录/参考文献等
- 本书可能是多卷/多部分合集，章节号可能重复（如出现两次「第1章」），重复号也各自保留
- 排除：正文里回顾/引用旧章的句子、「本书地图/内容总览」的条目、页眉页脚、文末章节清单
- 同一页出现多个标题时只取最像开篇的那个

输出 JSON 数组（不要多余文字）：[{{"level": 1|2, "title": "标题", "page_number": 物理页索引(0基)}}]
严格按 page_number 升序。"""
    entries = await _llm_toc(prompt)
    cleaned: list[dict] = []
    seen: set[tuple[int, int]] = set()
    for e in sorted(entries, key=lambda x: x.get("page_number", 0)):
        p = e.get("page_number", 0)
        lv = _entry_level(e)
        key = (p, lv)
        if 0 <= p < max(1, total_pages) and key not in seen:
            seen.add(key)
            cleaned.append({"level": lv, "title": e["title"], "page_number": p})
    logger.info("LLM 整理出 %d 个部分/章节", len(cleaned))
    return cleaned


def _parse_entries(text: str) -> list[dict]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return []
    entries = []
    for item in data:
        try:
            level = int(item.get("level", 2))
            page = int(item.get("page_number", 0))
        except (TypeError, ValueError):
            continue
        title = str(item.get("title", "")).strip()
        if title and page >= 0:
            entries.append({"level": level, "title": title, "page_number": page})
    return entries


# ---------------------------------------------------------------- 页码校准

def _detect_printed_number(page_text: str) -> int | None:
    """从页首/页尾的孤立数字行识别印刷页码。"""
    lines = [l.strip() for l in page_text.splitlines() if l.strip()]
    for i, ln in enumerate(lines):
        if i < 2 or i >= len(lines) - 2:
            if ln.isdigit() and len(ln) <= 4:
                return int(ln)
    return None


def calibrate_page_offset(pdf_path: str | Path, text_pages: list[str], entries: list[dict],
                          range_start_idx: int = 0) -> int:
    """印刷页码→物理页偏移。

    优先：用第一章标题在前 60 页内匹配物理页（更可靠）；
    兜底：孤立印刷页码启发式的偏移中位数。
    """
    if entries:
        first = entries[0]
        title = first["title"][:10]
        printed = first["page_number"]
        for rel, text in enumerate(text_pages[:60]):
            # 要求标题出现在页面开头（前 3 行以标题开头），避免误匹配目录页里的目录条目
            head = " ".join(text.splitlines()[:3]).strip()
            if title and head.startswith(title):
                return (range_start_idx + rel) - printed

    offsets: list[int] = []
    for rel, text in enumerate(text_pages):
        pn = _detect_printed_number(text)
        if pn is not None:
            offsets.append((range_start_idx + rel) - pn)
    if not offsets:
        return 0
    reasonable = [o for o in offsets if -5 <= o <= 60]
    offsets = reasonable or offsets
    offsets.sort()
    return offsets[len(offsets) // 2]


# ---------------------------------------------------------------- 章节范围（含校验与告警）

# 部分/卷/编 标题（分组节点）；须以「第X部/卷/编/篇」或「上/中/下卷/册」或英文 Part 开头
_PART_TITLE_RE = re.compile(
    r"^(第[一二三四五六七八九十百千万0-9]+[部卷编篇]|[上下中][卷册]|Part\s+[0-9IVXLC]+)",
    re.I,
)


def _entry_level(e: dict) -> int:
    """确定条目层级：1=部分/卷（分组），2=章。

    完全按标题判定，不信任 LLM 的 level（实测 LLM 常把所有条目都标 level 1）。
    部分/卷标题（第X部分/第X卷/第X编/上中下卷等）→ 分组；其余（第X章/前言/附录等）→ 章。
    """
    title = str(e.get("title", "")).strip()
    return 1 if _PART_TITLE_RE.match(title) else 2


def _leaf_count(nodes: list[dict]) -> int:
    """层级目录中叶子章节总数（分组只计其下的章）。"""
    return sum(len(n.get("children") or []) if n.get("level") == 1 else 1 for n in nodes)


def build_chapter_ranges(total_pages: int, entries: list[dict], offset: int,
                         range_start_idx: int = 0) -> tuple[list[dict], list[str]]:
    """把部分/章级目录换算为绝对物理页区间的层级树，返回 (nodes, warnings)。

    nodes: 顶层节点列表，每项 {title, start, end, level, children?}；
    level 1=部分/卷（children 为其下章），2=章（叶子）。
    start/end 为全书物理页 0 基；忽略空区间与疑似前言的小章节并给出告警。
    """
    warnings: list[str] = []
    chaps = sorted(entries, key=lambda e: e.get("page_number", 0))
    if not chaps:
        return [], ["未识别到任何部分或章节"]

    # 全序下逐条换算物理页区间（相邻共享边界页，保证相邻无缺页）
    raw: list[dict] = []
    for i, e in enumerate(chaps):
        start = _clamp(int(e["page_number"]) + offset, 0, total_pages - 1)
        if i + 1 < len(chaps):
            # 边界共享：本章结束页 = 下一条目起始页（该页同时归属相邻两章），保证无缺页
            end = _clamp(int(chaps[i + 1]["page_number"]) + offset, start, total_pages - 1)
        else:
            end = total_pages - 1
        raw.append({"title": e["title"], "start": start, "end": end,
                    "level": _entry_level(e), "children": []})

    # 过滤空区间
    non_empty = [r for r in raw if r["end"] >= r["start"]]
    for r in raw:
        if r["end"] < r["start"]:
            warnings.append(f"「{r['title']}」区间为空，已忽略")

    # 忽略范围首部疑似前言的极小章节（仅当还有其它内容且首节点是章时）
    nodes: list[dict] = []
    for i, r in enumerate(non_empty):
        span = r["end"] - r["start"] + 1
        is_front_matter = (len(non_empty) > 1 and i == 0 and r["level"] == 2
                           and span < 3 and (r["start"] - range_start_idx) <= 2
                           and not _FRONT_TITLE_RE.match(r["title"]))
        if is_front_matter:
            warnings.append(f"已忽略疑似前言「{r['title']}」（仅 {span} 页）")
            continue
        nodes.append(r)

    # 过小 / 占比过大的叶子章节告警（分组节点不计）
    total_span = max(1, (total_pages - 1) - range_start_idx + 1)
    for r in nodes:
        if r["level"] == 1:
            continue
        span = r["end"] - r["start"] + 1
        if span < 5:
            warnings.append(f"章节「{r['title']}」仅 {span} 页，请核对目录识别结果")
        if span / total_span > 0.9:
            warnings.append(f"章节「{r['title']}」占比过大（{span}/{total_span} 页），请核对目录识别结果")

    # 组装层级树：level 1 开启一个分组，其后 level 2 挂到该分组下
    tree: list[dict] = []
    current: dict | None = None
    for r in nodes:
        if r["level"] == 1:
            tree.append(r)
            current = r
        else:
            if current is not None:
                current["children"].append(r)
            else:
                tree.append(r)

    # 分组范围收紧到其下章节；无子章的分组退化为普通章节
    for g in tree:
        if g["level"] == 1:
            if g["children"]:
                g["start"] = min(g["start"], g["children"][0]["start"])
                g["end"] = max(g["end"], g["children"][-1]["end"])
            else:
                warnings.append(f"分组「{g['title']}」下没有章节，按普通章节保留")
                g["level"] = 2
                g.pop("children", None)
    return tree, warnings


def _ensure_front_matter(nodes: list[dict], text_pages: list[str],
                         range_start_idx: int = 0, warnings: list[str] | None = None) -> list[dict]:
    """正文前实质内容（前言/序/引言/致读者等）兜底补成一个顶层章节。

    仅当本次导入从书首开始（range_start_idx == 0）且首个顶层节点不在第 1 页时尝试；
    前置页需有实质文字（排除封面/版权等空页），且不是目录页（点线+页码）才补全。
    有些书的「前言」没有标题、直接以正文段落开头（如书信体），目录与标题扫描都识别不到，
    只能靠文本量兜底。补全后插入 nodes 首位，标题优先取识别到的前置标题，否则叫「前言」。
    """
    if warnings is None:
        warnings = []
    if range_start_idx != 0 or not nodes or nodes[0]["start"] <= 0:
        return nodes
    front = text_pages[:nodes[0]["start"]]
    joined = "\n".join(front)
    if len(joined.strip()) < 80:  # 封面/版权等几乎无实质文字
        return nodes
    toc_like = sum(1 for line in joined.splitlines() if _TOC_LINE_RE.match(line.strip()))
    if toc_like >= 1:  # 前置页含目录式行（点线+页码）→ 是目录/封面，不是正文前言
        return nodes
    title = "前言"
    for line in joined.splitlines()[:20]:
        m = _FRONT_TITLE_RE.match(line.strip())
        if m:
            title = m.group(1)
            break
    end = nodes[0]["start"] - 1
    nodes.insert(0, {"title": title, "start": 0, "end": end, "level": 2, "children": []})
    warnings.append(f"已补全前置内容「{title}」（第 1-{end + 1} 页）")
    return nodes


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


# ---------------------------------------------------------------- 子 PDF 切片

def split_pdf(pdf_path: str | Path, start: int, end: int, out_path: str | Path) -> None:
    """把原书 [start,end]（全书物理页）切片保存为子 PDF。"""
    import fitz
    src = fitz.open(str(pdf_path))
    dst = fitz.open()
    for pno in range(max(0, start), min(end + 1, src.page_count)):
        dst.insert_pdf(src, from_page=pno, to_page=pno)
    dst.save(str(out_path))
    dst.close()
    src.close()


# ---------------------------------------------------------------- 建章节 Document

async def create_chapter_documents(
    db: AsyncSession,
    project_id: str,
    pdf_path: str | Path,
    nodes: list[dict],
    base_sort_order: int = 0,
) -> list[Document]:
    """为层级目录创建分组 Document 与章节 Document（复用 ingest）。

    nodes: build_chapter_ranges 返回的层级树。
    分组(content_type='group')不切片子 PDF，只记录覆盖页码范围；
    章节写 book_file_path 与 page_start/page_end，供调节器重切使用。
    base_sort_order 用于分批导入续接排序。
    """
    docs: list[Document] = []
    sort = base_sort_order
    for node in nodes:
        title = node["title"] or f"第 {sort + 1} 章"
        if node.get("level") == 1:
            grp = await create_group_document(db, project_id, title,
                                              node["start"], node["end"], sort)
            docs.append(grp)
            sort += 1
            for ch in node.get("children") or []:
                ch_title = ch["title"] or f"第 {sort + 1} 章"
                doc = await create_chapter_from_book(
                    db, project_id, pdf_path, ch_title,
                    ch["start"], ch["end"], sort, parent_id=grp.id,
                )
                docs.append(doc)
                logger.info("章节落库: %s (pages %d-%d, 组 %s)",
                            ch_title, ch["start"] + 1, ch["end"] + 1, grp.title)
                sort += 1
        else:
            doc = await create_chapter_from_book(db, project_id, pdf_path, title,
                                                 node["start"], node["end"], sort)
            docs.append(doc)
            logger.info("章节落库: %s (pages %d-%d)", title, node["start"] + 1, node["end"] + 1)
            sort += 1
    return docs


async def create_group_document(
    db: AsyncSession,
    project_id: str,
    title: str,
    page_start: int | None,
    page_end: int | None,
    sort_order: int,
) -> Document:
    """创建一个分组 Document（部分/卷）：无文件/分块，记录覆盖页码范围。"""
    doc = Document(user_id=_LOCAL_USER_ID, title=title, filename="", file_path="",
                   content_type="group", chunk_count=0,
                   project_id=project_id, chapter_title=title, sort_order=sort_order,
                   page_start=page_start, page_end=page_end)
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


async def create_chapter_from_book(
    db: AsyncSession,
    project_id: str,
    book_path: str | Path,
    title: str,
    page_start: int,
    page_end: int,
    sort_order: int,
    parent_id: str | None = None,
) -> Document:
    """从整书 PDF 的 [page_start, page_end]（0 基含）切片生成一个章节 Document。"""
    from app.api.documents import ingest_document_file

    out_dir = Path(settings.document_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{project_id[:8]}_ch{sort_order + 1}.pdf"
    split_pdf(book_path, page_start, page_end, out_path)
    doc, _ = await ingest_document_file(  # ingest 返回 (Document, chunks)
        db, out_path, title=title,
        project_id=project_id, chapter_title=title, sort_order=sort_order,
    )
    doc.book_file_path = str(book_path)
    doc.page_start = int(page_start)
    doc.page_end = int(page_end)
    if parent_id:
        doc.parent_id = parent_id
    await db.commit()
    await db.refresh(doc)
    return doc


async def reslice_chapter(
    db: AsyncSession,
    doc: Document,
    book_path: str | Path,
    page_start: int,
    page_end: int,
    title: str,
) -> Document:
    """调节章节物理页范围：重切子 PDF + 重建 Chunk，保留 Document 身份。

    保留 Document（批注/总结/题目/闪卡不丢）；阅读单元随新子 PDF 自动更新。
    注：调整起始页可能使该章既有批注的 unit_index 偏移（结束页调整安全）。
    """
    out_dir = Path(settings.document_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{doc.id[:8]}_slice.pdf"
    split_pdf(book_path, page_start, page_end, out_path)

    # 重建 Chunk
    await db.execute(delete(Chunk).where(Chunk.document_id == doc.id))
    text, hints = parse_file(out_path)
    chunks_data = chunk_text(text, hints)
    for i, c in enumerate(chunks_data):
        db.add(Chunk(document_id=doc.id, seq=i, content=c["content"], heading=c["heading"]))

    doc.file_path = str(out_path)
    doc.chunk_count = len(chunks_data)
    doc.book_file_path = str(book_path)
    doc.page_start = int(page_start)
    doc.page_end = int(page_end)
    if title.strip():
        doc.title = title.strip()
        doc.chapter_title = title.strip()
    await db.commit()
    await db.refresh(doc)
    logger.info("章节重切: %s (pages %d-%d)", doc.title, page_start + 1, page_end + 1)
    return doc


async def cleanup_orphan_book_files(db: AsyncSession, book_path: str | Path) -> None:
    """若整书原 PDF 不再被任何章节引用，则删除该孤儿文件。"""
    path = str(book_path)
    refs = (await db.execute(select(Document.id).where(Document.book_file_path == path).limit(1))).scalars().first()
    if refs is None:
        try:
            Path(path).unlink(missing_ok=True)
            logger.info("清理孤儿整书文件: %s", path)
        except Exception as e:
            logger.warning("清理孤儿整书文件失败: %s", e)
