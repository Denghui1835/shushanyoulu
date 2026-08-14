"""老教授课堂 API — 大纲 / 开课 / 作答 / 完成。"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User
from app.core.course import get_outline, start_lesson, answer, complete_lesson

logger = logging.getLogger("yuanqi.api.course")
router = APIRouter(prefix="/api/course", tags=["course"])

LOCAL_USER_ID = "local_user"


async def get_or_create_user(db: AsyncSession) -> User:
    user = await db.get(User, LOCAL_USER_ID)
    if user is None:
        user = User(id=LOCAL_USER_ID, name="学习者")
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


class StartIn(BaseModel):
    topic: str


class AnswerIn(BaseModel):
    topic: str
    kind: str = "practice"      # practice / check
    answer: str = ""
    attempt: int = 1


class CompleteIn(BaseModel):
    topic: str


@router.get("")
async def outline(subject: str, db: AsyncSession = Depends(get_db)):
    """课程大纲：考点序列 + 已掌握标记 + 当前应学第几节。"""
    user = await get_or_create_user(db)
    return await get_outline(db, user, subject)


@router.post("/lesson")
async def lesson_start(subject: str, data: StartIn, db: AsyncSession = Depends(get_db)):
    """开始一节：老教授生成课程卡（讲解/陷阱/练习/检验）。"""
    user = await get_or_create_user(db)
    try:
        return await start_lesson(db, user, subject.strip(), data.topic.strip())
    except Exception as e:
        logger.exception("course lesson start failed")
        raise HTTPException(status_code=500, detail=f"开课失败：{e}")


@router.post("/answer")
async def lesson_answer(subject: str, data: AnswerIn, db: AsyncSession = Depends(get_db)):
    """老教授批改练习/检验：答对肯定，答错给提示，达上限拆解答案。"""
    user = await get_or_create_user(db)
    return await answer(db, user, subject.strip(), data.topic.strip(),
                        data.kind, data.answer.strip(), data.attempt)


@router.post("/complete")
async def lesson_complete(subject: str, data: CompleteIn, db: AsyncSession = Depends(get_db)):
    """标记本节已掌握，推进到下一节。"""
    user = await get_or_create_user(db)
    return await complete_lesson(db, user, subject.strip(), data.topic.strip())
