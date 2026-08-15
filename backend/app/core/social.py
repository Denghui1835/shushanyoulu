"""「一起学」社交发布助手：学习行为 → 动态，点赞 → 互相激励元气值。"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SocialPost, SocialLike, StudyLog

# 点赞激励规则：点赞者 +1，被赞者 +2（首次点赞才触发）
LIKE_GIVER_POINTS = 1
LIKE_RECEIVER_POINTS = 2


async def publish_activity(
    db: AsyncSession,
    user,
    kind: str,
    content: str,
    points: int = 0,
) -> SocialPost:
    """发布一条学习动态（学习行为自动触发）。"""
    post = SocialPost(
        user_id=user.id,
        username=(user.username or user.name or "学习者"),
        kind=kind,
        content=content,
        points=points,
    )
    db.add(post)
    await db.flush()
    return post


async def like_post(db: AsyncSession, post_id: str, user) -> dict:
    """点赞/取消点赞。首次点赞：点赞者 +1 元气值，动态作者 +2 元气值。"""
    post = await db.get(SocialPost, post_id)
    if not post:
        raise LookupError("动态不存在")
    if post.user_id == user.id:
        raise ValueError("不能给自己的动态点赞哦，快去给伙伴加油吧")

    existing = (await db.execute(
        select(SocialLike).where(
            SocialLike.post_id == post_id,
            SocialLike.user_id == user.id,
        )
    )).scalars().first()

    if existing:
        await db.delete(existing)
        await db.commit()
        count = await _like_count(db, post_id)
        return {"liked": False, "like_count": count, "points_gained": 0}

    db.add(SocialLike(post_id=post_id, user_id=user.id))
    # 互相激励：点赞者 +1，被赞者 +2（只有第一次点赞才给）
    db.add(StudyLog(
        user_id=user.id, kind="social", points=LIKE_GIVER_POINTS,
        detail=f"给「{post.username}」的学习动态点了赞，元气 +{LIKE_GIVER_POINTS}",
    ))
    if post.user_id != user.id:
        db.add(StudyLog(
            user_id=post.user_id, kind="social", points=LIKE_RECEIVER_POINTS,
            detail=f"你的动态被「{user.username or user.name}」点赞鼓励，元气 +{LIKE_RECEIVER_POINTS}",
        ))
    await db.commit()
    count = await _like_count(db, post_id)
    return {
        "liked": True,
        "like_count": count,
        "points_gained": LIKE_GIVER_POINTS,
        "author_points_gained": LIKE_RECEIVER_POINTS,
    }


async def _like_count(db: AsyncSession, post_id: str) -> int:
    from sqlalchemy import func
    return int((await db.execute(
        select(func.count()).select_from(SocialLike).where(SocialLike.post_id == post_id)
    )).scalar() or 0)
