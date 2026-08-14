"""统计看板 API：学习数据聚合，供应前端图表。

数据来源：
- check_ins：每日打卡天数、连续天数
- quiz_records：做题数、正确率、按日趋势
- flashcards：复习总量、FSRS 稳定性分布
- plan_tasks：任务完成趋势
- study_logs：元气值累积曲线、活动类型分布
"""
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import CheckIn, QuizRecord, Flashcard, PlanTask, StudyLog, Question

logger = logging.getLogger("yuanqi.api.stats")
router = APIRouter(prefix="/api/stats", tags=["stats"])

_WEEKS = 4   # 默认统计最近 4 周
_USER_ID = "local_user"


@router.get("/dashboard")
async def dashboard(db: AsyncSession = Depends(get_db)):
    """统计看板聚合数据：概览卡片 + 图表序列。"""
    now = datetime.now()
    week_ago = now - timedelta(days=_WEEKS * 7)

    # ── 概览卡片 ──
    overview = await _overview(db, week_ago, now)

    # ── 图表序列 ──
    daily_quiz = await _daily_quiz_trend(db, week_ago)
    daily_review = await _daily_review_trend(db, week_ago)
    daily_tasks = await _daily_task_trend(db, week_ago)
    points_curve = await _points_curve(db, week_ago)
    accuracy_trend = await _accuracy_trend(db, week_ago)

    # ── 薄弱点：错题最多的文档/知识点 ──
    weakness = await _weakness_analysis(db)

    # ── 活动分布（饼图） ──
    activity_breakdown = await _activity_breakdown(db, week_ago)

    return {
        "overview": overview,
        "charts": {
            "daily_quiz": daily_quiz,
            "daily_review": daily_review,
            "daily_tasks": daily_tasks,
            "points_curve": points_curve,
            "accuracy_trend": accuracy_trend,
        },
        "weakness": weakness,
        "activity_breakdown": activity_breakdown,
    }


# ═══════════════════════════════════════════════
# 概览卡片
# ═══════════════════════════════════════════════

async def _overview(db: AsyncSession, since: datetime, now: datetime) -> dict:
    """返回顶部 6 个概览数字。"""
    # 打卡天数（总计 + 本月）
    total_days = (await db.execute(
        select(func.count(CheckIn.id)).where(CheckIn.user_id == _USER_ID)
    )).scalar() or 0

    this_month = now.strftime("%Y-%m")
    monthly_days = (await db.execute(
        select(func.count(CheckIn.id)).where(
            CheckIn.user_id == _USER_ID,
            CheckIn.checkin_date.like(f"{this_month}%"),
        )
    )).scalar() or 0

    # 总做题数 + 正确率
    # SQLite boolean → 0/1 整数求 sum
    _correct_expr = case((QuizRecord.correct == True, 1), else_=0)
    total_quiz = (await db.execute(
        select(func.count(QuizRecord.id))
    )).scalar() or 0
    correct_quiz = (await db.execute(
        select(func.sum(_correct_expr))
    )).scalar() or 0
    accuracy = round(correct_quiz / total_quiz * 100, 1) if total_quiz > 0 else 0

    # 总复习闪卡数（reps > 0 即至少复习过一次）
    total_reviewed = (await db.execute(
        select(func.count(Flashcard.id)).where(
            Flashcard.reps > 0, Flashcard.discarded == False
        )
    )).scalar() or 0

    # 近 4 周做题数
    recent_quiz = (await db.execute(
        select(func.count(QuizRecord.id)).where(
            QuizRecord.created_at >= since
        )
    )).scalar() or 0

    # 近 4 周闪卡复习次数（用 reps 增量粗略估算）
    recent_reviewed = (await db.execute(
        select(func.count(Flashcard.id)).where(
            Flashcard.last_reviewed_at >= since,
            Flashcard.discarded == False,
        )
    )).scalar() or 0

    # 总元气值
    total_points = (await db.execute(
        select(func.coalesce(func.sum(StudyLog.points), 0)).where(
            StudyLog.user_id == _USER_ID
        )
    )).scalar() or 0

    # 连续打卡天数
    streak = await _calc_streak(db)

    return {
        "total_learning_days": total_days,
        "monthly_learning_days": monthly_days,
        "streak": streak,
        "total_quiz_count": total_quiz,
        "quiz_accuracy": accuracy,
        "total_reviewed_cards": total_reviewed,
        "recent_quiz_count": recent_quiz,
        "recent_reviewed_cards": recent_reviewed,
        "total_points": total_points,
    }


async def _calc_streak(db: AsyncSession) -> int:
    """从今天往回数连续打卡天数。"""
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    rows = (await db.execute(
        select(CheckIn.checkin_date).where(
            CheckIn.user_id == _USER_ID
        ).order_by(CheckIn.checkin_date.desc()).limit(366)
    )).scalars().all()

    if not rows:
        return 0

    # streak 必须始于今天或昨天
    if rows[0] not in (today, yesterday):
        return 0

    streak = 1
    for i in range(1, len(rows)):
        d1 = datetime.strptime(rows[i - 1], "%Y-%m-%d")
        d2 = datetime.strptime(rows[i], "%Y-%m-%d")
        if (d1 - d2).days == 1:
            streak += 1
        else:
            break
    return streak


# ═══════════════════════════════════════════════
# 图表时间序列
# ═══════════════════════════════════════════════

def _make_date_series(since: datetime, days: int) -> list[str]:
    """生成日期序列 ['08-01','08-02',...]（月-日）。"""
    return [(since + timedelta(days=i)).strftime("%m-%d") for i in range(days)]


async def _daily_quiz_trend(db: AsyncSession, since: datetime) -> list[dict]:
    """每日做题数趋势（近 4 周）。"""
    days = _WEEKS * 7
    rows = (await db.execute(
        select(
            func.strftime("%m-%d", QuizRecord.created_at).label("day"),
            func.count(QuizRecord.id).label("cnt"),
        ).where(
            QuizRecord.created_at >= since
        ).group_by("day").order_by("day")
    )).all()

    lookup = {r.day: r.cnt for r in rows}
    return [{"date": d, "count": lookup.get(d, 0)} for d in _make_date_series(since, days)]


async def _daily_review_trend(db: AsyncSession, since: datetime) -> list[dict]:
    """每日闪卡复习量趋势。"""
    days = _WEEKS * 7
    rows = (await db.execute(
        select(
            func.strftime("%m-%d", Flashcard.last_reviewed_at).label("day"),
            func.count(Flashcard.id).label("cnt"),
        ).where(
            Flashcard.last_reviewed_at >= since,
            Flashcard.discarded == False,
        ).group_by("day").order_by("day")
    )).all()

    lookup = {r.day: r.cnt for r in rows}
    return [{"date": d, "count": lookup.get(d, 0)} for d in _make_date_series(since, days)]


async def _daily_task_trend(db: AsyncSession, since: datetime) -> list[dict]:
    """每日完成任务数趋势。"""
    days = _WEEKS * 7
    rows = (await db.execute(
        select(
            func.substr(PlanTask.completed_at, 6, 5).label("day"),
            func.count(PlanTask.id).label("cnt"),
        ).where(
            PlanTask.status == "done",
            PlanTask.completed_at >= since.strftime("%Y-%m-%d %H:%M:%S"),
        ).group_by("day").order_by("day")
    )).all()

    lookup = {r.day: r.cnt for r in rows}
    return [{"date": d, "count": lookup.get(d, 0)} for d in _make_date_series(since, days)]


async def _points_curve(db: AsyncSession, since: datetime) -> list[dict]:
    """元气值累积曲线（每日新增点数）。"""
    days = _WEEKS * 7
    rows = (await db.execute(
        select(
            func.strftime("%m-%d", StudyLog.created_at).label("day"),
            func.coalesce(func.sum(StudyLog.points), 0).label("pts"),
        ).where(
            StudyLog.user_id == _USER_ID,
            StudyLog.created_at >= since,
            StudyLog.points > 0,
        ).group_by("day").order_by("day")
    )).all()

    lookup = {r.day: r.pts for r in rows}
    series = _make_date_series(since, days)
    cumulative = 0
    result = []
    for d in series:
        cumulative += lookup.get(d, 0)
        result.append({"date": d, "daily": lookup.get(d, 0), "cumulative": cumulative})
    return result


async def _accuracy_trend(db: AsyncSession, since: datetime) -> list[dict]:
    """每周正确率趋势（按周聚合）。"""
    _correct_expr = case((QuizRecord.correct == True, 1), else_=0)
    rows = (await db.execute(
        select(
            func.strftime("%Y-W%W", QuizRecord.created_at).label("week"),
            func.count(QuizRecord.id).label("total"),
            func.sum(_correct_expr).label("correct"),
        ).where(
            QuizRecord.created_at >= since
        ).group_by("week").order_by("week")
    )).all()

    return [{
        "week": r.week,
        "total": r.total,
        "correct": int(r.correct or 0),
        "accuracy": round(int(r.correct or 0) / r.total * 100, 1) if r.total > 0 else 0,
    } for r in rows]


# ═══════════════════════════════════════════════
# 薄弱点分析
# ═══════════════════════════════════════════════

async def _weakness_analysis(db: AsyncSession) -> list[dict]:
    """按文档统计错题最多的区域（薄弱点）。"""
    # 找出错题（有 quiz_record 且 correct=False），按题号去重后按文档分组
    wrong_qids = (
        select(QuizRecord.question_id).where(QuizRecord.correct == False).distinct()
    )
    rows = (await db.execute(
        select(
            Question.document_id,
            func.count(Question.id).label("wrong_count"),
        ).where(
            Question.id.in_(wrong_qids)
        ).group_by(Question.document_id).order_by(func.count(Question.id).desc()).limit(8)
    )).all()

    if not rows:
        return []

    # 查文档标题
    doc_ids = [r.document_id for r in rows]
    from app.models import Document
    docs = (await db.execute(
        select(Document.id, Document.title).where(Document.id.in_(doc_ids))
    )).all()
    title_map = {d.id: d.title for d in docs}

    return [{
        "document_id": r.document_id,
        "doc_title": title_map.get(r.document_id, "(已删除)"),
        "wrong_count": r.wrong_count,
    } for r in rows]


# ═══════════════════════════════════════════════
# 活动分布
# ═══════════════════════════════════════════════

async def _activity_breakdown(db: AsyncSession, since: datetime) -> list[dict]:
    """按活动类型统计次数分布（饼图）。"""
    rows = (await db.execute(
        select(
            StudyLog.kind,
            func.count(StudyLog.id).label("cnt"),
        ).where(
            StudyLog.user_id == _USER_ID,
            StudyLog.created_at >= since,
        ).group_by(StudyLog.kind).order_by(StudyLog.kind)
    )).all()

    KIND_LABEL = {
        "learn": "学习", "quiz": "做题", "flashcard": "复习",
        "chat": "问答", "plan": "计划", "checkin": "打卡",
    }
    return [{"kind": r.kind, "label": KIND_LABEL.get(r.kind, r.kind), "count": r.cnt} for r in rows]
