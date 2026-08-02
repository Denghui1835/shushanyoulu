"""学习计划与今日任务 API."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import LearningPlan, PlanTask, StudyLog, User, CheckIn

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
    await db.commit()
    total = (await db.execute(select(func.count()).select_from(CheckIn)
                              .where(CheckIn.user_id == LOCAL_USER_ID))).scalar()
    return {"checked_today": True, "streak": await _streak(db, LOCAL_USER_ID),
            "total": int(total or 0), "points_gained": _CHECKIN_POINTS}
