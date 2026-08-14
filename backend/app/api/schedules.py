"""手动计划表 API：整表 CRUD + 时间格 CRUD + 通知轮询 + 复制到下周。"""
import logging
import re
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.schedule import Schedule, ScheduleSlot, PlanNotification

logger = logging.getLogger("yuanqi.api.schedules")
router = APIRouter(prefix="/api/schedules", tags=["schedules"])

_TIME_RE = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')


def _validate_hhmm(v: str | None) -> str | None:
    if v is not None and not _TIME_RE.match(v):
        raise ValueError(f"时间格式须为 HH:mm（如 08:00），收到: {v}")
    return v


# ── 序列化 ──

def _slot_out(s: ScheduleSlot) -> dict:
    return {
        "id": s.id, "schedule_id": s.schedule_id,
        "day_of_week": s.day_of_week, "start_time": s.start_time,
        "end_time": s.end_time, "title": s.title,
        "description": s.description, "color": s.color,
        "sort_order": s.sort_order,
        "notify_on_start": bool(s.notify_on_start),
        "completed": bool(s.completed),
    }

def _sched_out(s: Schedule, slots: list[ScheduleSlot]) -> dict:
    return {
        "id": s.id, "project_id": s.project_id, "title": s.title,
        "week_start_date": s.week_start_date,
        "created_at": s.created_at.isoformat(),
        "slots": [_slot_out(sl) for sl in sorted(slots, key=lambda x: (x.day_of_week, x.sort_order, x.start_time))],
    }


# ── 默认时间格 ──

def _default_slots_for_day(day: int) -> list[dict]:
    return [
        {"day_of_week": day, "start_time": "08:00", "end_time": "09:00", "title": "", "color": "#f6ffed", "description": ""},
        {"day_of_week": day, "start_time": "09:00", "end_time": "10:30", "title": "", "color": "#e6f4ff", "description": ""},
        {"day_of_week": day, "start_time": "10:30", "end_time": "12:00", "title": "", "color": "#f6ffed", "description": ""},
        {"day_of_week": day, "start_time": "14:00", "end_time": "15:30", "title": "", "color": "#fff7e6", "description": ""},
        {"day_of_week": day, "start_time": "15:30", "end_time": "17:00", "title": "", "color": "#f9f0ff", "description": ""},
        {"day_of_week": day, "start_time": "19:00", "end_time": "20:30", "title": "", "color": "#e6f4ff", "description": ""},
        {"day_of_week": day, "start_time": "20:30", "end_time": "22:00", "title": "", "color": "#f6ffed", "description": ""},
    ]


# ═══════════════════════════════════════
# 整表 CRUD
# ═══════════════════════════════════════

class ScheduleIn(BaseModel):
    project_id: str
    title: str = "本周计划"
    week_start_date: str  # YYYY-MM-DD（周一）

@router.get("")
async def list_schedules(project_id: str = "", db: AsyncSession = Depends(get_db)):
    """列出日/周计划表。不传 project_id 则全量。"""
    q = select(Schedule).order_by(Schedule.week_start_date.desc(), Schedule.created_at.desc())
    if project_id:
        q = q.where(Schedule.project_id == project_id)
    rows = (await db.execute(q)).scalars().all()

    if not rows:
        return {"schedules": []}

    sched_ids = [r.id for r in rows]
    slot_rows = (await db.execute(
        select(ScheduleSlot).where(ScheduleSlot.schedule_id.in_(sched_ids))
    )).scalars().all()
    slots_by_sched: dict[str, list[ScheduleSlot]] = {}
    for sl in slot_rows:
        slots_by_sched.setdefault(sl.schedule_id, []).append(sl)

    return {"schedules": [_sched_out(r, slots_by_sched.get(r.id, [])) for r in rows]}


@router.post("")
async def create_schedule(data: ScheduleIn, db: AsyncSession = Depends(get_db)):
    """新建周计划表（自动填默认时间格）。"""
    sched = Schedule(project_id=data.project_id, title=data.title, week_start_date=data.week_start_date)
    db.add(sched)
    await db.flush()

    sort_i = 0
    for day in range(7):
        for ds in _default_slots_for_day(day):
            slot = ScheduleSlot(schedule_id=sched.id, sort_order=sort_i, **ds)
            db.add(slot)
            sort_i += 1

    await db.commit()
    await db.refresh(sched)

    slots = (await db.execute(
        select(ScheduleSlot).where(ScheduleSlot.schedule_id == sched.id)
    )).scalars().all()
    return _sched_out(sched, list(slots))


@router.get("/{sched_id}")
async def get_schedule(sched_id: str, db: AsyncSession = Depends(get_db)):
    sched = await db.get(Schedule, sched_id)
    if not sched:
        raise HTTPException(status_code=404, detail="计划表不存在")
    slots = (await db.execute(
        select(ScheduleSlot).where(ScheduleSlot.schedule_id == sched_id)
    )).scalars().all()
    return _sched_out(sched, list(slots))


class SchedUpdateIn(BaseModel):
    title: str | None = None

@router.put("/{sched_id}")
async def update_schedule(sched_id: str, data: SchedUpdateIn, db: AsyncSession = Depends(get_db)):
    sched = await db.get(Schedule, sched_id)
    if not sched:
        raise HTTPException(status_code=404, detail="计划表不存在")
    if data.title is not None:
        sched.title = data.title
    await db.commit()
    return {"ok": True}


@router.delete("/{sched_id}")
async def delete_schedule(sched_id: str, db: AsyncSession = Depends(get_db)):
    sched = await db.get(Schedule, sched_id)
    if not sched:
        raise HTTPException(status_code=404, detail="计划表不存在")
    await db.execute(delete(ScheduleSlot).where(ScheduleSlot.schedule_id == sched_id))
    await db.delete(sched)
    await db.commit()
    return {"ok": True}


# ═══════════════════════════════════════
# 时间格 CRUD（HH:mm 校验）
# ═══════════════════════════════════════

class SlotIn(BaseModel):
    day_of_week: int = 0
    start_time: str = "08:00"
    end_time: str = "09:00"
    title: str = ""
    description: str = ""
    color: str = "#e6f4ff"
    sort_order: int = 0
    notify_on_start: bool = False
    completed: bool = False

    @field_validator("start_time", "end_time")
    @classmethod
    def _check_time(cls, v: str | None) -> str | None:
        return _validate_hhmm(v)


class SlotUpdateIn(BaseModel):
    day_of_week: int | None = None
    start_time: str | None = None
    end_time: str | None = None
    title: str | None = None
    description: str | None = None
    color: str | None = None
    sort_order: int | None = None
    notify_on_start: bool | None = None
    completed: bool | None = None

    @field_validator("start_time", "end_time")
    @classmethod
    def _check_time(cls, v: str | None) -> str | None:
        return _validate_hhmm(v)


@router.post("/{sched_id}/slots")
async def add_slot(sched_id: str, data: SlotIn, db: AsyncSession = Depends(get_db)):
    sched = await db.get(Schedule, sched_id)
    if not sched:
        raise HTTPException(status_code=404, detail="计划表不存在")
    slot = ScheduleSlot(schedule_id=sched_id, **data.model_dump())
    db.add(slot)
    await db.commit()
    await db.refresh(slot)
    return _slot_out(slot)


@router.put("/{sched_id}/slots/{slot_id}")
async def update_slot(sched_id: str, slot_id: str, data: SlotUpdateIn, db: AsyncSession = Depends(get_db)):
    slot = await db.get(ScheduleSlot, slot_id)
    if not slot or slot.schedule_id != sched_id:
        raise HTTPException(status_code=404, detail="时间格不存在")
    update_data = data.model_dump(exclude_none=True)
    for k, v in update_data.items():
        setattr(slot, k, v)
    await db.commit()
    await db.refresh(slot)
    return _slot_out(slot)


@router.delete("/{sched_id}/slots/{slot_id}")
async def delete_slot(sched_id: str, slot_id: str, db: AsyncSession = Depends(get_db)):
    slot = await db.get(ScheduleSlot, slot_id)
    if not slot or slot.schedule_id != sched_id:
        raise HTTPException(status_code=404, detail="时间格不存在")
    await db.delete(slot)
    await db.commit()
    return {"ok": True}


# ── 批量更新某一天的所有槽位 ──

class BulkSlotIn(BaseModel):
    id: str | None = None
    start_time: str = "08:00"
    end_time: str = "09:00"
    title: str = ""
    description: str = ""
    color: str = "#e6f4ff"
    sort_order: int = 0
    notify_on_start: bool = False
    completed: bool = False

    @field_validator("start_time", "end_time")
    @classmethod
    def _check_time(cls, v: str | None) -> str | None:
        return _validate_hhmm(v)


class DaySlotsIn(BaseModel):
    slots: list[BulkSlotIn]

@router.put("/{sched_id}/day/{day_of_week}")
async def update_day_slots(sched_id: str, day_of_week: int, data: DaySlotsIn, db: AsyncSession = Depends(get_db)):
    """批量更新某天的全部时间格。"""
    sched = await db.get(Schedule, sched_id)
    if not sched:
        raise HTTPException(status_code=404, detail="计划表不存在")

    existing = (await db.execute(
        select(ScheduleSlot).where(
            ScheduleSlot.schedule_id == sched_id,
            ScheduleSlot.day_of_week == day_of_week,
        )
    )).scalars().all()

    existing_map = {s.id: s for s in existing}
    received_ids: set[str] = set()

    for i, ds in enumerate(data.slots):
        if ds.id and ds.id in existing_map:
            slot = existing_map[ds.id]
            for k in ("start_time", "end_time", "title", "description", "color", "notify_on_start", "completed"):
                setattr(slot, k, getattr(ds, k))
            slot.sort_order = i
            received_ids.add(ds.id)
        else:
            new_slot = ScheduleSlot(
                schedule_id=sched_id, day_of_week=day_of_week, sort_order=i,
                start_time=ds.start_time, end_time=ds.end_time,
                title=ds.title, description=ds.description, color=ds.color,
                notify_on_start=ds.notify_on_start,
                completed=ds.completed,
            )
            db.add(new_slot)

    for sid in existing_map:
        if sid not in received_ids:
            await db.delete(existing_map[sid])

    await db.commit()

    result = (await db.execute(
        select(ScheduleSlot).where(
            ScheduleSlot.schedule_id == sched_id,
            ScheduleSlot.day_of_week == day_of_week,
        ).order_by(ScheduleSlot.sort_order)
    )).scalars().all()
    return {"slots": [_slot_out(s) for s in result]}


# ═══════════════════════════════════════
# 复制到下周
# ═══════════════════════════════════════

@router.post("/{sched_id}/copy-to-next-week")
async def copy_to_next_week(sched_id: str, db: AsyncSession = Depends(get_db)):
    """复制当前周计划到下一周（week_start_date +7 天），含全部时间格和 notify 设置。"""
    sched = await db.get(Schedule, sched_id)
    if not sched:
        raise HTTPException(status_code=404, detail="计划表不存在")

    slots = (await db.execute(
        select(ScheduleSlot).where(ScheduleSlot.schedule_id == sched_id)
    )).scalars().all()

    next_monday = date.fromisoformat(sched.week_start_date) + timedelta(days=7)
    new_sched = Schedule(
        project_id=sched.project_id,
        title=f"{sched.title}（续）",
        week_start_date=next_monday.isoformat(),
    )
    db.add(new_sched)
    await db.flush()

    for sl in slots:
        db.add(ScheduleSlot(
            schedule_id=new_sched.id,
            day_of_week=sl.day_of_week,
            start_time=sl.start_time,
            end_time=sl.end_time,
            title=sl.title,
            description=sl.description,
            color=sl.color,
            sort_order=sl.sort_order,
            notify_on_start=sl.notify_on_start,
            completed=sl.completed,
        ))

    await db.commit()
    await db.refresh(new_sched)

    new_slots = (await db.execute(
        select(ScheduleSlot).where(ScheduleSlot.schedule_id == new_sched.id)
    )).scalars().all()
    return _sched_out(new_sched, list(new_slots))


# ═══════════════════════════════════════
# 通知轮询：前端定时调用，返回当前应通知的槽位
# ═══════════════════════════════════════

@router.get("/notifications/pending")
async def pending_notifications(db: AsyncSession = Depends(get_db)):
    """前端轮询：返回当前时间 ±1 分钟内 begin、notify_on_start=true 且尚未通知的槽位。

    前端拿到后调用浏览器 Notification API 弹出通知，
    然后调用 POST /schedules/notifications/ack 标记已通知。
    """
    now = date.today()
    now_str = now.isoformat()
    weekday = now.weekday()  # 0=Monday
    now_time = _now_hhmm()

    # 查找今天的活跃计划表
    today_scheds = (await db.execute(
        select(Schedule).where(Schedule.week_start_date <= now_str)
    )).scalars().all()

    if not today_scheds:
        return {"slots": []}

    # 找出本周的计划表（week_start_date 最近的）
    today_scheds.sort(key=lambda s: s.week_start_date)
    active = today_scheds[-1]  # 最新的一张表

    if active.week_start_date > now_str:
        # 本周尚未开始
        return {"slots": []}

    slots = (await db.execute(
        select(ScheduleSlot).where(
            ScheduleSlot.schedule_id == active.id,
            ScheduleSlot.day_of_week == weekday,
            ScheduleSlot.notify_on_start == True,
            ScheduleSlot.title != "",
        )
    )).scalars().all()

    if not slots:
        return {"slots": []}

    # 过滤：时间在 ±1 分钟内 且 今天尚未通知
    result = []
    for sl in slots:
        if not _time_within(sl.start_time, now_time, minutes=1):
            continue
        # 查是否已通知
        already = (await db.execute(
            select(func.count(PlanNotification.id)).where(
                PlanNotification.slot_id == sl.id,
                PlanNotification.notify_date == now_str,
            )
        )).scalar() or 0
        if already > 0:
            continue
        result.append(_slot_out(sl))

    return {"slots": result}


class AckNotificationIn(BaseModel):
    slot_ids: list[str]

@router.post("/notifications/ack")
async def ack_notifications(data: AckNotificationIn, db: AsyncSession = Depends(get_db)):
    """标记通知已发送（防重复）。"""
    today = date.today().isoformat()
    count = 0
    for sid in data.slot_ids:
        slot = await db.get(ScheduleSlot, sid)
        if not slot:
            continue
        pn = PlanNotification(schedule_id=slot.schedule_id, slot_id=sid, notify_date=today)
        db.add(pn)
        count += 1
    await db.commit()
    return {"acked": count}


def _now_hhmm() -> str:
    from datetime import datetime
    return datetime.now().strftime("%H:%M")

def _time_within(target: str, now: str, minutes: int = 1) -> bool:
    """检查 target 是否在 now 的 ±minutes 分钟内。"""
    try:
        th, tm = int(target[:2]), int(target[3:5])
        nh, nm = int(now[:2]), int(now[3:5])
        diff = abs((th * 60 + tm) - (nh * 60 + nm))
        return diff <= minutes
    except (ValueError, IndexError):
        return False
