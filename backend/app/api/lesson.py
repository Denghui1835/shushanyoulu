"""深度教学 API — 讲→考→判→评 的一对一教学模式."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User, TopicProgress
from app.core.lesson import start_lesson, answer_lesson, end_lesson, get_curriculum

logger = logging.getLogger("yuanqi.api.lesson")
router = APIRouter(prefix="/api/lesson", tags=["lesson"])

LOCAL_USER_ID = "local_user"


async def get_or_create_user(db: AsyncSession) -> User:
    user = await db.get(User, LOCAL_USER_ID)
    if user is None:
        user = User(id=LOCAL_USER_ID, name="学习者")
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


class LessonStartIn(BaseModel):
    subject: str = ""      # 学科，如 3DGS / 数学建模
    topic: str = ""        # 知识点


class ProgressIn(BaseModel):
    subject: str
    topic: str
    status: str = "mastered"   # learning / mastered / review


@router.get("/curriculum")
async def curriculum():
    """课程目录：各学科的知识点列表（零基础学习者从这里点菜）。"""
    return get_curriculum()


@router.get("/progress")
async def list_progress(db: AsyncSession = Depends(get_db)):
    """深度教学学习进度：已学考点 + 掌握状态。"""
    user = await get_or_create_user(db)
    rows = (await db.execute(
        select(TopicProgress).where(TopicProgress.user_id == user.id).order_by(TopicProgress.updated_at.desc())
    )).scalars().all()
    return {
        "count": len(rows),
        "items": [{"subject": r.subject, "topic": r.topic, "status": r.status, "times": r.times} for r in rows],
    }


@router.post("/progress")
async def set_progress(data: ProgressIn, db: AsyncSession = Depends(get_db)):
    """标记考点进度：mastered 已掌握 / review 待复习。"""
    user = await get_or_create_user(db)
    row = (await db.execute(
        select(TopicProgress).where(
            TopicProgress.user_id == user.id,
            TopicProgress.subject == data.subject.strip(),
            TopicProgress.topic == data.topic.strip(),
        )
    )).scalars().first()
    if row:
        row.status = data.status
    else:
        db.add(TopicProgress(user_id=user.id, subject=data.subject.strip(),
                             topic=data.topic.strip(), status=data.status, times=0))
    await db.commit()
    return {"ok": True, "subject": data.subject.strip(), "topic": data.topic.strip(), "status": data.status}


class LessonAnswerIn(BaseModel):
    lesson_id: str
    answer: str


@router.post("/start")
async def start(data: LessonStartIn, db: AsyncSession = Depends(get_db)):
    """开启一次深度教学，返回第一张卡（讲解 + 题目）。"""
    user = await get_or_create_user(db)
    try:
        return await start_lesson(db, user, data.subject.strip(), data.topic.strip())
    except Exception as e:
        logger.exception("lesson start failed")
        raise HTTPException(status_code=500, detail=f"教学开启失败：{e}")


@router.post("/answer")
async def answer(data: LessonAnswerIn, db: AsyncSession = Depends(get_db)):
    """提交作答：返回判断结果 + 点评 + 下一张卡（或 done）。"""
    user = await get_or_create_user(db)
    try:
        return await answer_lesson(db, user, data.lesson_id, data.answer.strip())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("lesson answer failed")
        raise HTTPException(status_code=500, detail=f"作答处理失败：{e}")


@router.post("/{lesson_id}/end")
async def end(lesson_id: str, db: AsyncSession = Depends(get_db)):
    """提前结束教学。"""
    user = await get_or_create_user(db)
    try:
        return await end_lesson(db, user, lesson_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("lesson end failed")
        raise HTTPException(status_code=500, detail=f"结束失败：{e}")
