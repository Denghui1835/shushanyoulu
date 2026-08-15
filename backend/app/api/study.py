"""学习计划与今日任务 API."""
from datetime import date, timedelta, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import LearningPlan, PlanTask, StudyLog, User, CheckIn, SocialPost

router = APIRouter(prefix="/api/study", tags=["study"])

LOCAL_USER_ID = "local_user"


@router.get("/plan")
async def get_plan(db: AsyncSession = Depends(get_db)):
    user = await db.get(User, LOCAL_USER_ID)
    if not user or not user.active_plan_id:
        return {"plan": None, "tasks": []}
    plan = await db.get(LearningPlan, user.active_plan_id)
    if not plan:
        return {"plan": None, "tasks": []}
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


@router.post("/tasks/{task_id}/complete")
async def complete_task(task_id: str, db: AsyncSession = Depends(get_db)):
    task = await db.get(PlanTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    task.status = "done"
    db.add(StudyLog(user_id=LOCAL_USER_ID, kind="plan", detail=f"完成任务「{task.title}」", points=5))
    db.add(SocialPost(user_id=LOCAL_USER_ID, username="学习者", kind="task",
                      content=f"完成任务「{task.title}」，元气 +5 ⚡", points=5))
    await db.commit()
    return {"ok": True}


@router.get("/activity")
async def activity(limit: int = 10, db: AsyncSession = Depends(get_db)):
    logs = (await db.execute(
        select(StudyLog).order_by(StudyLog.created_at.desc()).limit(limit)
    )).scalars().all()
    return [{
        "kind": l.kind, "detail": l.detail, "points": l.points,
        "created_at": l.created_at.isoformat(),
    } for l in logs]


# ---------------------------------------------------------------- 每日打卡

_CHECKIN_POINTS = 10


async def _streak(db: AsyncSession, user_id: str) -> int:
    """连续打卡天数：从今天（或昨天）往前数连续有打卡的天数。"""
    rows = (await db.execute(
        select(CheckIn.checkin_date).where(CheckIn.user_id == user_id)
    )).scalars().all()
    dates = set(rows)
    streak = 0
    d = date.today()
    if d.strftime("%Y-%m-%d") not in dates:
        d -= timedelta(days=1)  # 今天还没打卡，从昨天算，不中断 streak
    while d.strftime("%Y-%m-%d") in dates:
        streak += 1
        d -= timedelta(days=1)
    return streak


@router.get("/checkin")
async def get_checkin(db: AsyncSession = Depends(get_db)):
    today = date.today().strftime("%Y-%m-%d")
    checked = (await db.execute(
        select(CheckIn).where(CheckIn.user_id == LOCAL_USER_ID,
                              CheckIn.checkin_date == today).limit(1)
    )).scalars().first()
    total = (await db.execute(
        select(func.count()).select_from(CheckIn).where(CheckIn.user_id == LOCAL_USER_ID)
    )).scalar()
    return {"checked_today": bool(checked), "streak": await _streak(db, LOCAL_USER_ID),
            "total": int(total or 0)}


@router.post("/checkin")
async def do_checkin(db: AsyncSession = Depends(get_db)):
    today = date.today().strftime("%Y-%m-%d")
    existing = (await db.execute(
        select(CheckIn).where(CheckIn.user_id == LOCAL_USER_ID,
                              CheckIn.checkin_date == today).limit(1)
    )).scalars().first()
    if existing:
        return {"checked_today": True, "streak": await _streak(db, LOCAL_USER_ID),
                "total": (await db.execute(select(func.count()).select_from(CheckIn)
                          .where(CheckIn.user_id == LOCAL_USER_ID))).scalar(),
                "points_gained": 0}
    db.add(CheckIn(user_id=LOCAL_USER_ID, checkin_date=today, points=_CHECKIN_POINTS))
    db.add(StudyLog(user_id=LOCAL_USER_ID, kind="plan", detail="今日打卡",
                    points=_CHECKIN_POINTS))
    streak = await _streak(db, LOCAL_USER_ID)
    user = await db.get(User, LOCAL_USER_ID)
    db.add(SocialPost(
        user_id=LOCAL_USER_ID,
        username=(user.username or user.name or "学习者") if user else "学习者",
        kind="checkin",
        content=f"完成了今日打卡，连续打卡 {streak} 天 🔥",
        points=_CHECKIN_POINTS,
    ))
    await db.commit()
    total = (await db.execute(select(func.count()).select_from(CheckIn)
                              .where(CheckIn.user_id == LOCAL_USER_ID))).scalar()
    return {"checked_today": True, "streak": await _streak(db, LOCAL_USER_ID),
            "total": int(total or 0), "points_gained": _CHECKIN_POINTS}


# ---------------------------------------------------------------- 继续学习（最近学习上下文）

class ContextIn(BaseModel):
    project_id: str | None = None
    project_title: str | None = None
    subject: str | None = None
    topic: str | None = None


def _context_payload(u: User) -> dict | None:
    if not u.last_activity_at:
        return None
    return {
        "project_id": u.last_project_id,
        "project_title": u.last_project_title,
        "subject": u.last_subject,
        "topic": u.last_topic,
        "updated_at": u.last_activity_at.isoformat(),
    }


@router.get("/context")
async def get_context(db: AsyncSession = Depends(get_db)):
    """最近学习上下文（首页「继续学习」用）。"""
    user = await db.get(User, LOCAL_USER_ID)
    return {"context": _context_payload(user) if user else None}


@router.post("/context")
async def set_context(data: ContextIn, db: AsyncSession = Depends(get_db)):
    """记录最近学习位置：打开书 / 开始一节课时调用。"""
    user = await db.get(User, LOCAL_USER_ID)
    if not user:
        user = User(id=LOCAL_USER_ID, name="学习者")
        db.add(user)
    if data.project_id is not None:
        user.last_project_id = data.project_id or None
    if data.project_title is not None:
        user.last_project_title = data.project_title or None
    if data.subject is not None:
        user.last_subject = data.subject or None
    if data.topic is not None:
        user.last_topic = data.topic or None
    user.last_activity_at = datetime.now()
    await db.commit()
    return {"context": _context_payload(user)}
