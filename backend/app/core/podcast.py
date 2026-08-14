"""AI 播客文稿生成：把某个阅读单元（章节/页）的文本做成双人主播对谈脚本。

对标豆包 AI 播客：两位主播（主播A 女声 / 主播B 男声）围绕核心知识点自然对话，
口语化、有情感起伏、有过渡衔接，覆盖重点与易错点。

设计对齐 summarize.py：
- 复用 get_reading_units 取该单元文本，超长截断（_MAX_SRC_CHARS）
- 先删旧记录再重建（幂等可重跑），状态机 generating/done/error
- 异常落 error 不抛给前端；文稿要求可被 _parse_turns 解析为双人对话，否则判失败
"""
import logging
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.api_scheduler import api_client
from app.core.api_scheduler.adapters.base import AdapterConfig
from app.core.reading_content import get_reading_units
from app.models import Document, PodcastScript

logger = logging.getLogger("yuanqi.podcast")

_MAX_SRC_CHARS = 9000        # 源文本截断（约 6000 tokens，对齐 summarize）
_MAX_TURNS = 40              # 对谈句数上限（防失控）
_TURN_RE = re.compile(r"^\s*(主播[AB])\s*[：:]\s*(.+)$")


# ---------------------------------------------------------------- 文稿解析

def parse_turns(content: str) -> list[dict]:
    """把文稿解析为说话轮次 [{speaker, text}]；非「主播A/B：」行跳过并告警。

    speaker 取「主播A」/「主播B」原样，供 TTS 选音色。
    超 _MAX_TURNS 时截断并 warn，避免末尾内容静默丢失。
    """
    turns: list[dict] = []
    non_matching: list[str] = []
    for line in (content or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        m = _TURN_RE.match(stripped)
        if not m:
            non_matching.append(stripped)
            continue
        text = m.group(2).strip()
        if text:
            turns.append({"speaker": m.group(1), "text": text})

    if non_matching:
        logger.warning("播客文稿有 %d 行非对话格式被丢弃: %s",
                       len(non_matching), non_matching[:5])

    if len(turns) > _MAX_TURNS:
        logger.warning("播客文稿超过 %d 轮上限，截断丢弃末尾 %d 轮 — 音频将不完整",
                       _MAX_TURNS, len(turns) - _MAX_TURNS)

    return turns[: _MAX_TURNS]


def _is_valid_script(content: str) -> bool:
    """文稿至少 2 轮且两位主播都出场才算有效。"""
    turns = parse_turns(content)
    speakers = {t["speaker"] for t in turns}
    return len(turns) >= 2 and speakers == {"主播A", "主播B"}


# ---------------------------------------------------------------- 生成

def _build_script_prompt(doc_title: str, unit_title: str, src: str, truncated: bool = False) -> str:
    truncation_hint = ""
    if truncated:
        truncation_hint = (
            "\n注意：以上资料内容较长，已被截断为前 {max_chars} 字。"
            "请从**全篇**中提炼 3-6 个最核心的知识点来展开对谈，"
            "不要只覆盖截断部分的前半段内容——末尾的要点同样重要。"
        ).format(max_chars=_MAX_SRC_CHARS)
    return f"""你是一档知识播客「书山电台」的编剧。请为《{doc_title}》中「{unit_title}」这一期写一份双人对谈文稿。

=== 主播人设 ===
主播A（女生，晓晓）：好奇心强，喜欢用生动的类比和故事来解释概念，语速略快、情绪饱满。常用句式：「哇，这个太有意思了！」「那如果……会怎么样？」「让我用一个生活中的例子来解释……」

主播B（男生，云希）：逻辑清晰，喜欢追问"为什么"，善于点出反直觉的洞察和常见误区，偶尔打趣主播A。常用句式：「等等，这里有个关键点……」「很多人会这样想，但其实……」「我补充一个容易被忽略的细节……」

=== 结构要求 ===
1. **开场钩子**（2-3 句）：用一个问题/场景/反常识现象引入，让听众立刻产生兴趣。禁止说「今天我们来聊聊XX」这种平淡开场
2. **核心展开**：围绕 2-4 个核心观点展开对谈，每个观点先解释再延伸
3. **易错点拨**：至少点名 1-2 个常见误区或学生容易踩的坑
4. **收尾金句**：用一句话总结本期的核心收获，让听众听完想记笔记

=== 对话风格 ===
- 像两个真正懂行的人在咖啡馆聊天——有笑声、有争论、有即兴发挥，不是在念PPT
- 能举生活例子的绝不干讲概念；能一句话说清的绝不绕弯子
- 适时表达惊讶、赞同或善意的质疑（「真的吗？」「我觉得还可以换个角度……」「对，而且我刚好想到……」）
- 不要堆砌「首先/其次/最后」，用自然过渡代替

=== 格式要求 ===
- 每句独立成行，行首严格以「主播A：」或「主播B：」开头（半角冒号），句末用中文标点
- 两位主播交替发言，同一人连续不超过 3 句
- 全文 1000-1800 字（口播约 3-5 分钟），信息密度要高——每一轮对话都在推进话题，不要原地绕圈

{truncation_hint}
资料内容：
{src}"""


async def _get_unit(db: AsyncSession, document: Document, unit_index: int) -> dict | None:
    units = await get_reading_units(db, document)
    if 0 <= unit_index < len(units):
        return units[unit_index]
    return None


async def generate_podcast_script(db: AsyncSession, document: Document, unit_index: int) -> PodcastScript:
    """为某阅读单元生成播客文稿。先删旧记录再重建（幂等）；异常落 error 不抛给前端。"""
    old = (await db.execute(select(PodcastScript).where(
        PodcastScript.document_id == document.id, PodcastScript.unit_index == unit_index
    ))).scalars().first()
    if old:
        # 文稿变了，旧音频不再匹配，一并清理
        await _delete_audio(old)
        await db.delete(old)
        await db.commit()

    script = PodcastScript(document_id=document.id, unit_index=unit_index, status="generating")
    db.add(script)
    await db.commit()
    await db.refresh(script)

    try:
        unit = await _get_unit(db, document, unit_index)
        if not unit:
            raise ValueError(f"章节单元 {unit_index} 不存在或无内容")
        src = unit["text"][: _MAX_SRC_CHARS]
        source_truncated = len(unit["text"]) > _MAX_SRC_CHARS
        if source_truncated:
            logger.warning("播客源文本过长（%d 字），截断为 %d 字。LLM 可能看不到末尾内容",
                           len(unit["text"]), _MAX_SRC_CHARS)
        if len(src) < 20:
            raise ValueError("该章节文本过短，不足以生成播客")
        prompt = _build_script_prompt(document.title, unit["title"], src, truncated=source_truncated)
        adapter = api_client.get_adapter(settings.default_model)
        resp = await adapter.chat_completion(
            [{"role": "user", "content": prompt}],
            AdapterConfig(temperature=0.8, max_tokens=2500, timeout=settings.request_timeout),
        )
        content = (resp.content or "").strip()
        if not content:
            raise ValueError("模型返回为空")
        if not _is_valid_script(content):
            raise ValueError("文稿不是有效的双人对谈格式，请重新生成")
        script.content = content
        script.status = "done"
        logger.info("播客文稿 done: doc=%s unit=%s (%d 字, %d 轮)",
                    document.id, unit_index, len(content), len(parse_turns(content)))
    except Exception as e:
        logger.warning("播客文稿生成失败: doc=%s unit=%s: %s", document.id, unit_index, e)
        script.status = "error"
        script.error = f"文稿生成失败：{str(e)[:200]}"

    await db.commit()
    await db.refresh(script)
    return script


async def update_podcast_script(db: AsyncSession, document: Document, unit_index: int,
                                content: str) -> PodcastScript:
    """手动直接保存文稿内容（不经 AI）：校验双人对谈格式，改动后清空旧音频。"""
    script = (await db.execute(select(PodcastScript).where(
        PodcastScript.document_id == document.id, PodcastScript.unit_index == unit_index
    ))).scalars().first()
    if not script or script.status != "done" or not script.content:
        raise ValueError("请先生成播客文稿，再编辑")

    content = content.strip()
    if not content:
        raise ValueError("文稿不能为空")
    if not _is_valid_script(content):
        raise ValueError("文稿不是有效的双人对谈格式（每行需以「主播A：」或「主播B：」开头）")

    script.prev_content = script.content   # 记录上一步，供撤回
    script.content = content
    script.status = "done"
    await _delete_audio(script)
    script.audio_path = None
    await db.commit()
    await db.refresh(script)
    logger.info("播客文稿已手动保存: doc=%s unit=%s (%d 字)", document.id, unit_index, len(content))
    return script


async def undo_podcast_script(db: AsyncSession, document: Document, unit_index: int) -> PodcastScript:
    """撤回上一步修改：恢复上次修改前的文稿，并清空旧音频。"""
    script = (await db.execute(select(PodcastScript).where(
        PodcastScript.document_id == document.id, PodcastScript.unit_index == unit_index
    ))).scalars().first()
    if not script or script.status != "done" or not script.content:
        raise ValueError("请先生成播客文稿")
    if not script.prev_content:
        raise ValueError("没有可撤回的上一步")
    script.content = script.prev_content
    script.prev_content = None
    await _delete_audio(script)
    script.audio_path = None
    await db.commit()
    await db.refresh(script)
    logger.info("播客文稿已撤回: doc=%s unit=%s", document.id, unit_index)
    return script


async def _delete_audio(script: PodcastScript) -> None:
    """删除文稿关联的音频文件与实测时长（如有）。"""
    if script.audio_path:
        try:
            from pathlib import Path
            Path(script.audio_path).unlink(missing_ok=True)
        except Exception as e:
            logger.warning("清理播客音频失败: %s", e)
    script.audio_seconds = None


# ---------------------------------------------------------------- 文稿修改（打字/语音指令）

_EDIT_PROMPT_TEMPLATE = """请根据用户要求，修改下面这期双人 AI 播客的对话文稿。

本期播客对应：{unit_title}

原文稿：
{script}

用户修改要求：
{instruction}

要求：
- 只输出修改后的完整文稿，不要任何多余文字
- 严格保持「主播A：」/「主播B：」双人对谈格式，每句独立成行，两位主播交替发言
- 保持口语化、有情感、有过渡衔接
- 修改幅度贴合用户要求：小改就局部调整，大改就整体重写"""


async def edit_podcast_script(db: AsyncSession, document: Document, unit_index: int,
                              instruction: str) -> PodcastScript:
    """按用户指令（打字/语音）修改播客文稿。改动后清空旧音频（须重新合成）。"""
    script = (await db.execute(select(PodcastScript).where(
        PodcastScript.document_id == document.id, PodcastScript.unit_index == unit_index
    ))).scalars().first()
    if not script or script.status != "done" or not script.content:
        raise ValueError("请先生成播客文稿，再修改")

    unit = await _get_unit(db, document, unit_index)
    unit_title = unit["title"] if unit else f"第 {unit_index + 1} 单元"
    prompt = _EDIT_PROMPT_TEMPLATE.format(unit_title=unit_title,
                                          script=script.content, instruction=instruction)
    adapter = api_client.get_adapter(settings.default_model)
    resp = await adapter.chat_completion(
        [{"role": "user", "content": prompt}],
        AdapterConfig(temperature=0.8, max_tokens=2500, timeout=settings.request_timeout),
    )
    content = (resp.content or "").strip()
    if not content:
        raise ValueError("模型返回为空，请重试")
    if not _is_valid_script(content):
        raise ValueError("修改后的文稿不是有效的双人对谈格式，请换个说法重试")

    script.prev_content = script.content   # 记录上一步，供撤回
    script.content = content
    script.status = "done"
    await _delete_audio(script)
    script.audio_path = None
    await db.commit()
    await db.refresh(script)
    logger.info("播客文稿已修改: doc=%s unit=%s (%d 字)", document.id, unit_index, len(content))
    return script
