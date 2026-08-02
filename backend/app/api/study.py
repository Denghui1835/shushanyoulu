"""学习计划与今日任务 API."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import LearningPlan, PlanTask, StudyLog, User

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
