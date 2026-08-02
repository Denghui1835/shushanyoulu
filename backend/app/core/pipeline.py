"""全链路生成 pipeline：知识树 → 题目 → 闪卡."""
import logging
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.knowledge import generate_knowledge_tree
from app.core.quiz import generate_questions
from app.core.memory import generate_flashcards
from app.models import Document, StudyLog

logger = logging.getLogger("yuanqi.pipeline")


async def run_pipeline(db: AsyncSession, document_id: str) -> AsyncIterator[dict]:
    """Run the full generation pipeline, yielding progress events.

    Events: {"stage": "knowledge"|"quiz"|"flashcards"|"done", "message": str, ...}
    """
    doc = await db.get(Document, document_id)
    if not doc:
        yield {"stage": "error", "message": "文档不存在"}
        return

    yield {"stage": "knowledge", "message": "正在生成知识树…"}
    kp = await generate_knowledge_tree(db, document_id)
    yield {"stage": "knowledge_done", "message": f"知识树完成（{len(kp)} 个节点）", "count": len(kp)}

    yield {"stage": "quiz", "message": "正在生成题目…"}
    qs = await generate_questions(db, document_id)
    yield {"stage": "quiz_done", "message": f"题目完成（{len(qs)} 道）", "count": len(qs)}

    yield {"stage": "flashcards", "message": "正在生成闪卡…"}
    cards = await generate_flashcards(db, document_id)
    yield {"stage": "flashcards_done", "message": f"闪卡完成（{len(cards)} 张）", "count": len(cards)}

    db.add(StudyLog(user_id=doc.user_id, kind="plan",
                    detail=f"对《{doc.title}》跑完全链路生成", points=10))
    await db.commit()
    yield {"stage": "done", "message": "全部生成完成 🎉", "counts": {"kp": len(kp), "qs": len(qs), "cards": len(cards)}}
