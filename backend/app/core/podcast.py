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
    """把文稿解析为说话轮次 [{speaker, text}]；非「主播A/B：」行跳过。

    speaker 取「主播A」/「主播B」原样，供 TTS 选音色。
    """
    turns: list[dict] = []
    for line in (content or "").splitlines():
        m = _TURN_RE.match(line.strip())
        if not m:
            continue
        text = m.group(2).strip()
        if text:
            turns.append({"speaker": m.group(1), "text": text})
    return turns[: _MAX_TURNS]


def _is_valid_script(content: str) -> bool:
    """文稿至少 2 轮且两位主播都出场才算有效。"""
    turns = parse_turns(content)
    speakers = {t["speaker"] for t in turns}
    return len(turns) >= 2 and speakers == {"主播A", "主播B"}


# ---------------------------------------------------------------- 生成

def _build_script_prompt(doc_title: str, unit_title: str, src: str) -> str:
    return f"""请把学习资料《{doc_title}》中「{unit_title}」这一部分，做成一期「双人 AI 播客」的对话文稿。

两位主播「主播A」（温暖亲切的女声）与「主播B」（沉稳爽朗的男声）围绕这部分内容自然对谈，
像两个朋友在聊天，而不是照本宣科地朗读课文。

要求：
- 口语化、有情感起伏、语气自然；多用过渡衔接语（如「接下来我们聊聊…」「说到这儿，我突然想到…」「那这一点要怎么记呢？」「对对对，我补充一句…」）
- 覆盖本部分的核心知识点、重点与易错点，穿插一问一答、互相补充、互相打趣
- 每句独立成行，行首严格以「主播A：」或「主播B：」开头（半角冒号），句末用中文标点
- 两位主播交替发言，同一人连续不超过 3 句
- 全文 800-1600 字（约 2-4 分钟播讲），不要出现「主播A」之外的主持人角色

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
        if len(src) < 20:
            raise ValueError("该章节文本过短，不足以生成播客")
        prompt = _build_script_prompt(document.title, unit["title"], src)
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


async def _delete_audio(script: PodcastScript) -> None:
    """删除文稿关联的音频文件（如有）。"""
    if script.audio_path:
        try:
            from pathlib import Path
            Path(script.audio_path).unlink(missing_ok=True)
        except Exception as e:
            logger.warning("清理播客音频失败: %s", e)
