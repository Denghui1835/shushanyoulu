"""伴学 API — 对话(SSE)、学习计划、学习状态."""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import (
    User, ChatSession, ChatMessage, LearningPlan, PlanTask, StudyLog,
)
from app.core.companion import generate_plan, adjust_plan, stream_chat, build_context, _today_str, generate_wizard_plan
from app.core.memory import due_count

logger = logging.getLogger("yuanqi.api.companion")
router = APIRouter(prefix="/api/companion", tags=["companion"])

LOCAL_USER_ID = "local_user"


async def get_or_create_user(db: AsyncSession) -> User:
    user = await db.get(User, LOCAL_USER_ID)
    if user is None:
        user = User(id=LOCAL_USER_ID, name="学习者")
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


class ProfileIn(BaseModel):
    name: str | None = None
    goal: str | None = None
    goal_detail: str | None = None
    daily_minutes: int | None = None


@router.get("/profile")
async def get_profile(db: AsyncSession = Depends(get_db)):
    user = await get_or_create_user(db)
    return {
        "name": user.name,
        "goal": user.goal,
        "goal_detail": user.goal_detail,
        "daily_minutes": user.daily_minutes,
        "onboarded": user.is_onboarded,
    }


@router.post("/profile")
async def update_profile(data: ProfileIn, db: AsyncSession = Depends(get_db)):
    user = await get_or_create_user(db)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    await db.commit()
    return {"ok": True, "onboarded": user.is_onboarded}


@router.get("/session")
async def get_or_create_session(db: AsyncSession = Depends(get_db)):
    user = await get_or_create_user(db)
    session = (await db.execute(
        select(ChatSession).where(ChatSession.user_id == user.id).order_by(ChatSession.updated_at.desc())
    )).scalars().first()
    if session is None:
        session = ChatSession(user_id=user.id, title="与小书虫的对话")
        db.add(session)
        await db.commit()
        await db.refresh(session)
    return {"id": session.id, "title": session.title}


@router.get("/messages")
async def list_messages(session_id: str, db: AsyncSession = Depends(get_db)):
    msgs = (await db.execute(
        select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at)
    )).scalars().all()
    return [{"id": m.id, "role": m.role, "content": m.content,
             "created_at": m.created_at.isoformat()} for m in msgs]


class ChatIn(BaseModel):
    session_id: str
    message: str


@router.post("/chat")
async def chat(data: ChatIn, db: AsyncSession = Depends(get_db)):
    """SSE streaming companion chat."""
    try:
        gen = await stream_chat(db, data.session_id, data.message)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    async def event_stream():
        try:
            async for delta in gen:
                yield f"data: {json.dumps({'type': 'delta', 'content': delta}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"
        yield "data: {\"type\": \"done\"}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


class PlanIn(BaseModel):
    goal: str | None = None
    goal_detail: str | None = None
    daily_minutes: int | None = None


class PlanWizardIn(BaseModel):
    courses: list[str] = []        # 想学的课程/知识点
    time_slots: list[str] = []     # 有空的时段，如 ["早上", "晚上"]
    daily_minutes: int = 30
    total_days: int = 7


@router.post("/plan/wizard")
async def create_wizard_plan(data: PlanWizardIn, db: AsyncSession = Depends(get_db)):
    """AI 一键生成计划表：按选定的课程 + 空余时段排布每日计划。"""
    user = await get_or_create_user(db)
    if not data.courses:
        raise HTTPException(status_code=400, detail="请至少选择一门想学的课程")
    try:
        plan = await generate_wizard_plan(
            db, user,
            courses=data.courses,
            time_slots=data.time_slots,
            daily_minutes=max(10, min(480, data.daily_minutes)),
            total_days=max(1, min(60, data.total_days)),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"计划生成失败：{e}")

    tasks = (await db.execute(
        select(PlanTask).where(PlanTask.plan_id == plan.id).order_by(PlanTask.day_index)
    )).scalars().all()
    return {
        "plan": {"id": plan.id, "title": plan.title, "summary": plan.summary,
                 "total_days": plan.total_days, "status": plan.status},
        "tasks": [{
            "id": t.id, "day": t.day_index, "scheduled_date": t.scheduled_date,
            "title": t.title, "description": t.description, "type": t.task_type,
            "status": t.status,
        } for t in tasks],
    }


@router.post("/plan")
async def create_plan(data: PlanIn | None = None, db: AsyncSession = Depends(get_db)):
    """Generate a study plan from the learner profile (+ optional inline goal/time)."""
    user = await get_or_create_user(db)
    if data:
        if data.goal is not None:
            user.goal = data.goal
        if data.goal_detail is not None:
            user.goal_detail = data.goal_detail
        if data.daily_minutes is not None:
            user.daily_minutes = data.daily_minutes
        await db.commit()

    if not user.goal.strip():
        raise HTTPException(status_code=400, detail="请先告诉我你的学习目标")

    try:
        plan = await generate_plan(db, user)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"计划生成失败：{e}")

    tasks = (await db.execute(
        select(PlanTask).where(PlanTask.plan_id == plan.id).order_by(PlanTask.day_index)
    )).scalars().all()
    return {
        "plan": {
            "id": plan.id, "title": plan.title, "summary": plan.summary,
            "total_days": plan.total_days, "status": plan.status,
        },
        "tasks": [{
            "id": t.id, "day": t.day_index, "scheduled_date": t.scheduled_date,
            "title": t.title, "description": t.description, "type": t.task_type,
            "status": t.status,
        } for t in tasks],
    }


@router.post("/plan/adjust")
async def adjust_plan_endpoint(db: AsyncSession = Depends(get_db)):
    """动态调整计划：按当前进度重排剩余学习安排，生成新的活跃计划。"""
    user = await get_or_create_user(db)
    if not user.goal.strip():
        raise HTTPException(status_code=400, detail="请先告诉我你的学习目标")
    try:
        plan = await adjust_plan(db, user)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"计划调整失败：{e}")
    tasks = (await db.execute(
        select(PlanTask).where(PlanTask.plan_id == plan.id).order_by(PlanTask.day_index)
    )).scalars().all()
    return {
        "plan": {"id": plan.id, "title": plan.title, "summary": plan.summary,
                 "total_days": plan.total_days, "status": plan.status},
        "tasks": [{
            "id": t.id, "day": t.day_index, "scheduled_date": t.scheduled_date,
            "title": t.title, "description": t.description, "type": t.task_type,
            "status": t.status,
        } for t in tasks],
    }


@router.get("/status")
async def status(db: AsyncSession = Depends(get_db)):
    """Full learning snapshot for the home screen."""
    user = await get_or_create_user(db)
    ctx = await build_context(db, user, "")
    due = await due_count(db)

    return {
        "user": {"name": user.name, "goal": user.goal, "daily_minutes": user.daily_minutes,
                 "onboarded": user.is_onboarded},
        "continue": ({
            "project_id": user.last_project_id,
            "project_title": user.last_project_title,
            "subject": user.last_subject,
            "topic": user.last_topic,
            "updated_at": user.last_activity_at.isoformat() if user.last_activity_at else None,
        } if user.last_activity_at else None),
        "plan": ctx["plan"],
        "today_tasks": ctx["today_tasks"],
        "due_cards_count": due,
        "due_cards_preview": ctx["due_cards"],
        "points": ctx["points"],
        "recent_activity": ctx["recent_activity"],
    }
