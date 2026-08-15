"""「一起学」社交 API — 学习动态流、点赞鼓励、每周学习排行榜."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.auth import get_optional_user
from app.core.social import like_post
from app.models import User, SocialPost, SocialLike, StudyLog, CheckIn

router = APIRouter(prefix="/api/social", tags=["social"])


async def _actor(db: AsyncSession, request: Request) -> User:
    """当前用户：登录账号优先，否则本地主人（local_user）。"""
    u = await get_optional_user(request, db)
    if u:
        return u
    user = await db.get(User, "local_user")
    if user is None:
        user = User(id="local_user", name="学习者")
        db.add(user)
        await db.flush()
    return user


@router.get("/feed")
async def feed(limit: int = 50, request: Request = None, db: AsyncSession = Depends(get_db)):
    """最新学习动态（自动发布：打卡/任务/课程/模拟），含点赞数与我是否赞过。"""
    actor = await _actor(db, request)
    posts = (await db.execute(
        select(SocialPost).order_by(SocialPost.created_at.desc()).limit(min(limit, 200))
    )).scalars().all()
    ids = [p.id for p in posts]
    counts: dict[str, int] = {}
    liked_ids: set[str] = set()
    if ids:
        for pid, n in (await db.execute(
            select(SocialLike.post_id, func.count())
            .where(SocialLike.post_id.in_(ids)).group_by(SocialLike.post_id)
        )).all():
            counts[pid] = int(n)
        liked_ids = set((await db.execute(
            select(SocialLike.post_id).where(
                SocialLike.user_id == actor.id,
                SocialLike.post_id.in_(ids),
            )
        )).scalars().all())
    return {
        "items": [{
            "id": p.id,
            "username": p.username or "学习者",
            "kind": p.kind,
            "content": p.content,
            "points": p.points,
            "like_count": counts.get(p.id, 0),
            "liked_by_me": p.id in liked_ids,
            "mine": p.user_id == actor.id,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        } for p in posts],
    }


@router.post("/posts/{post_id}/like")
async def like_endpoint(post_id: str, request: Request = None, db: AsyncSession = Depends(get_db)):
    """点赞/取消点赞；首次点赞：点赞者 +1，动态作者 +2 元气值。"""
    actor = await _actor(db, request)
    try:
        return await like_post(db, post_id, actor)
    except LookupError:
        raise HTTPException(status_code=404, detail="动态不存在")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/leaderboard")
async def leaderboard(days: int = 7, request: Request = None, db: AsyncSession = Depends(get_db)):
    """学习排行榜：近 N 天累计元气值 + 打卡天数（互相激励的榜单）。"""
    since = datetime.now() - timedelta(days=max(1, min(days, 90)))
    rows = (await db.execute(
        select(StudyLog.user_id, func.sum(StudyLog.points), func.count())
        .where(StudyLog.created_at >= since)
        .group_by(StudyLog.user_id)
        .order_by(func.sum(StudyLog.points).desc())
        .limit(10)
    )).all()
    user_ids = [r[0] for r in rows]
    names: dict[str, str] = {}
    if user_ids:
        for u in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all():
            names[u.id] = u.username or u.name or "学习者"
    checkins: dict[str, int] = {}
    if user_ids:
        for uid, n in (await db.execute(
            select(CheckIn.user_id, func.count()).where(
                CheckIn.user_id.in_(user_ids),
                CheckIn.checkin_date >= since.strftime("%Y-%m-%d"),
            ).group_by(CheckIn.user_id)
        )).all():
            checkins[uid] = int(n)
    return {
        "days": days,
        "items": [{
            "user_id": uid,
            "name": names.get(uid, "学习者"),
            "points": int(points or 0),
            "checkins": checkins.get(uid, 0),
        } for uid, points, _ in rows],
    }
