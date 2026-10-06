"""管理后台：用户管理（列表 / 重置密码 / 停用 / 删除）。

管理员唯一，就是认领了 `local_user` 行的那个账号（首个注册者）——
见 `models/user.py` 的 `is_admin` 与 `api/auth.py::register` 的首个账号分支。

**级联删除为什么长这样**：SQLite 这边模型里**没有声明任何外键**（`auth_tokens`、
`documents` 等全是裸字符串列），所以没有 `ON DELETE CASCADE` 可依赖，只能手写。
手写三十来张表最大的风险不是漏表，而是「预览说删 3 条、实际删了 5 条」——
于是这里把级联定义成**一张有序的步骤表** `_cascade_steps()`，预览拿它 `COUNT`、
删除拿它 `DELETE`，同一份数据驱动两条路径，不可能漂移。
步骤顺序照抄 `api/documents.py::delete_document_cascade` 里已验证过的次序
（答题记录先于题目、知识树子节点先于父节点、消息先于会话）。

**共享音频绝不删**：听读音频是内容寻址的（`listen_tts.cache_key()` =
sha256(文本|音色|语速|引擎)），一段音频可能被多个用户、多个仓库共用，
删账号只清 `PodcastScript.audio_path`（旧版按文稿存的、非共享）与
`Document.file_path`（该文档自己的原件）。
"""
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.auth import _extract_token, hash_password, require_admin, revoke_all_tokens
from app.database import get_db
from app.models import (
    Annotation, APICallLog, APIQuota, AuthToken, BlankCache, ChatMessage, ChatSession,
    CheckIn, Chunk, DocSummary, Document, Drawing, Episode, Flashcard, KanbanCard,
    KanbanColumn, KnowledgePoint, LearningPlan, Lesson, MockRecord, PlaybackProgress,
    PlanTask, PodcastScript, Project, ProjectFork, ProjectStar, ProjectSuggestion,
    Question, QuizRecord, Schedule, ScheduleSlot, SocialLike, SocialPost, StudyLog,
    TopicProgress, User,
)
from app.models.schedule import PlanNotification

logger = logging.getLogger("yuanqi.api.admin")
router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------------------------------------------------------------- 级联：单一事实来源

async def _collect(db: AsyncSession, uid: str) -> dict:
    """一次性算出所有下级 id 集合 —— 预览与删除共用，保证两者看到同一批数据。"""
    async def ids(stmt) -> list[str]:
        return list((await db.execute(stmt)).scalars().all())

    project_ids = await ids(select(Project.id).where(Project.user_id == uid))
    doc_ids = await ids(select(Document.id).where(
        or_(Document.user_id == uid, Document.project_id.in_(project_ids))))
    episode_ids = await ids(select(Episode.id).where(
        or_(Episode.user_id == uid, Episode.project_id.in_(project_ids))))
    return {
        "uid": uid,
        "project_ids": project_ids,
        "doc_ids": doc_ids,
        "q_ids": await ids(select(Question.id).where(Question.document_id.in_(doc_ids))),
        "kp_ids": await ids(select(KnowledgePoint.id).where(
            KnowledgePoint.document_id.in_(doc_ids))),
        "plan_ids": await ids(select(LearningPlan.id).where(LearningPlan.user_id == uid)),
        "session_ids": await ids(select(ChatSession.id).where(ChatSession.user_id == uid)),
        "column_ids": await ids(select(KanbanColumn.id).where(
            KanbanColumn.project_id.in_(project_ids))),
        "schedule_ids": await ids(select(Schedule.id).where(
            Schedule.project_id.in_(project_ids))),
        "post_ids": await ids(select(SocialPost.id).where(SocialPost.user_id == uid)),
        "episode_ids": episode_ids,
    }


def _cascade_steps(c: dict) -> list[tuple[str, type, object]]:
    """有序级联步骤表 —— **单一事实来源**，预览与删除都只认它。

    每一步 = (中文名, ORM 模型, where 条件)。空 id 集合会生成恒假条件，
    匹配 0 行，所以不必为「有没有数据」写分支。
    """
    uid = c["uid"]
    P, D = c["project_ids"], c["doc_ids"]
    Q, KP = c["q_ids"], c["kp_ids"]
    PL, SESS = c["plan_ids"], c["session_ids"]
    COL, SCH = c["column_ids"], c["schedule_ids"]
    POST, EPI = c["post_ids"], c["episode_ids"]
    return [
        # —— 文档内容树（先子后父）——
        ("答题记录", QuizRecord, QuizRecord.question_id.in_(Q)),
        ("知识点（子节点）", KnowledgePoint,
         (KnowledgePoint.document_id.in_(D)) & (KnowledgePoint.parent_id.in_(KP))),
        ("知识点", KnowledgePoint, KnowledgePoint.document_id.in_(D)),
        ("题目", Question, Question.document_id.in_(D)),
        ("文档分块", Chunk, Chunk.document_id.in_(D)),
        ("闪卡", Flashcard, Flashcard.document_id.in_(D)),
        ("批注", Annotation, Annotation.document_id.in_(D)),
        ("文档摘要", DocSummary, DocSummary.document_id.in_(D)),
        ("播客文稿", PodcastScript, PodcastScript.document_id.in_(D)),
        ("绘制", Drawing, Drawing.document_id.in_(D)),
        ("挖空缓存", BlankCache, BlankCache.document_id.in_(D)),
        # —— 计划 / 聊天 ——
        ("计划任务", PlanTask,
         or_(PlanTask.plan_id.in_(PL), PlanTask.document_id.in_(D))),
        ("聊天消息", ChatMessage, ChatMessage.session_id.in_(SESS)),
        ("聊天会话", ChatSession, ChatSession.id.in_(SESS)),
        ("学习计划", LearningPlan, LearningPlan.user_id == uid),
        # —— 看板 ——
        ("看板卡片", KanbanCard, KanbanCard.column_id.in_(COL)),
        ("看板列", KanbanColumn, KanbanColumn.id.in_(COL)),
        # —— 日程 ——
        ("日程提醒", PlanNotification, PlanNotification.schedule_id.in_(SCH)),
        ("日程时段", ScheduleSlot, ScheduleSlot.schedule_id.in_(SCH)),
        ("日程", Schedule, Schedule.id.in_(SCH)),
        # —— 社交 / 社区 ——
        ("点赞", SocialLike, or_(SocialLike.post_id.in_(POST), SocialLike.user_id == uid)),
        ("动态", SocialPost, SocialPost.user_id == uid),
        ("收藏", ProjectStar, or_(ProjectStar.project_id.in_(P), ProjectStar.user_id == uid)),
        ("协作建议", ProjectSuggestion,
         or_(ProjectSuggestion.project_id.in_(P), ProjectSuggestion.user_id == uid)),
        ("Fork 记录", ProjectFork,
         or_(ProjectFork.user_id == uid, ProjectFork.from_project_id.in_(P),
             ProjectFork.new_project_id.in_(P))),
        # —— 听读 ——
        ("播放进度", PlaybackProgress,
         or_(PlaybackProgress.user_id == uid, PlaybackProgress.document_id.in_(D),
             PlaybackProgress.episode_id.in_(EPI))),
        ("讲次", Episode, or_(Episode.user_id == uid, Episode.project_id.in_(P))),
        # —— 文档与仓库本体 ——
        ("文档", Document, Document.id.in_(D)),
        ("仓库", Project, Project.user_id == uid),
        # —— 用户自己的零散记录 ——
        ("登录令牌", AuthToken, AuthToken.user_id == uid),
        ("打卡", CheckIn, CheckIn.user_id == uid),
        ("课程卡学习", Lesson, Lesson.user_id == uid),
        ("模拟考记录", MockRecord, MockRecord.user_id == uid),
        ("学习日志", StudyLog, StudyLog.user_id == uid),
        ("知识点进度", TopicProgress, TopicProgress.user_id == uid),
        ("API 调用日志", APICallLog, APICallLog.user_id == uid),
        ("API 配额", APIQuota, APIQuota.user_id == uid),
        # —— 最后才是用户本人 ——
        ("用户", User, User.id == uid),
    ]


async def _preview_counts(db: AsyncSession, c: dict) -> dict[str, int]:
    """按同一张步骤表 COUNT —— 只列出非零项，免得预览里全是 0 看着累。"""
    out: dict[str, int] = {}
    for label, model, cond in _cascade_steps(c):
        n = int((await db.execute(
            select(func.count()).select_from(model).where(cond))).scalar() or 0)
        if n:
            out[label] = n
    return out


async def _unlink_files(db: AsyncSession, c: dict) -> int:
    """删除磁盘文件。只碰「这份文档自己的」文件，共享的音频缓存一概不碰。"""
    removed = 0
    paths: list[str] = []
    if c["doc_ids"]:
        paths += [p for p in (await db.execute(
            select(PodcastScript.audio_path).where(
                PodcastScript.document_id.in_(c["doc_ids"]),
                PodcastScript.audio_path.is_not(None)))).scalars().all() if p]
        paths += [p for p in (await db.execute(
            select(Document.file_path).where(
                Document.id.in_(c["doc_ids"]), Document.file_path.is_not(None))
        )).scalars().all() if p]
    for p in paths:
        try:
            Path(p).unlink(missing_ok=True)
            removed += 1
        except OSError as e:  # 文件被占用/权限问题不该让整个删除失败
            logger.warning("删除用户文件失败（已跳过）%s: %s", p, e)
    return removed


# ---------------------------------------------------------------- 守卫

async def _admin_count(db: AsyncSession) -> int:
    return int((await db.execute(
        select(func.count()).select_from(User).where(User.is_admin.is_(True))
    )).scalar() or 0)


async def _load_target(db: AsyncSession, uid: str) -> User:
    u = await db.get(User, uid)
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    return u


def _guard_self(admin: User, target: User, action: str) -> None:
    if target.id == admin.id:
        raise HTTPException(status_code=400, detail=f"不能{action}自己的账号")


async def _guard_last_admin(db: AsyncSession, target: User, action: str) -> None:
    if target.is_admin and await _admin_count(db) <= 1:
        raise HTTPException(status_code=400, detail=f"不能{action}最后一个管理员")


# ---------------------------------------------------------------- 接口

@router.get("/users")
async def list_users(admin: User = Depends(require_admin),
                     db: AsyncSession = Depends(get_db)):
    """全部账号概览 + 全站汇总。"""
    users = (await db.execute(select(User).order_by(User.created_at))).scalars().all()
    counts = dict((await db.execute(
        select(Project.user_id, func.count()).group_by(Project.user_id))).all())
    token_counts = dict((await db.execute(
        select(AuthToken.user_id, func.count()).group_by(AuthToken.user_id))).all())

    rows = [{
        "id": u.id,
        "username": u.username or "",
        "name": u.name,
        "created_at": u.created_at.isoformat() if u.created_at else None,
        "last_activity_at": u.last_activity_at.isoformat() if u.last_activity_at else None,
        "project_count": int(counts.get(u.id, 0)),
        "session_count": int(token_counts.get(u.id, 0)),
        "is_admin": bool(u.is_admin),
        "is_active": bool(u.is_active),
        "has_password": bool(u.password_hash),
        "has_wechat": bool(u.wechat_openid),
        "is_self": u.id == admin.id,
    } for u in users]

    # 单机模式（allow_anonymous_local=True）下任何人丢掉 token 都会被当成 local_user
    # （也就是主人）——此时封禁其实防不住谁。如实告诉用户，别让人以为已经管住了。
    warning = None
    if settings.allow_anonymous_local:
        warning = ("当前是单机模式（allow_anonymous_local=True）：不带登录令牌的请求会被"
                   "当作本机主人处理，因此「停用」在公开部署前并不能真正拦住人。"
                   "正式对外时请在 backend/.env 设 ALLOW_ANONYMOUS_LOCAL=false。")

    return {
        "users": rows,
        "total": len(rows),
        "admin_count": sum(1 for u in users if u.is_admin),
        "warning": warning,
    }


class ResetPasswordIn(BaseModel):
    new_password: str


@router.post("/users/{uid}/reset-password")
async def reset_password(uid: str, data: ResetPasswordIn, request: Request,
                         admin: User = Depends(require_admin),
                         db: AsyncSession = Depends(get_db)):
    """管理员给账号重设密码，并强制其下线（否则旧令牌仍然有效，改了等于没改）。"""
    target = await _load_target(db, uid)
    pwd = data.new_password or ""
    if len(pwd) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 位")
    target.password_hash = hash_password(pwd)
    # 改自己密码时保留当前会话，别把管理员自己踢出去
    keep = _extract_token(request) if target.id == admin.id else None
    revoked = await revoke_all_tokens(db, target.id, keep=keep)
    await db.commit()
    logger.info("管理员 %s 重置了 %s 的密码，踢下线 %d 个会话", admin.id, target.id, revoked)
    return {"ok": True, "revoked_tokens": revoked}


class SetActiveIn(BaseModel):
    is_active: bool


@router.post("/users/{uid}/active")
async def set_active(uid: str, data: SetActiveIn, admin: User = Depends(require_admin),
                     db: AsyncSession = Depends(get_db)):
    """停用 / 启用账号。停用时顺带吊销其全部令牌。"""
    target = await _load_target(db, uid)
    if not data.is_active:
        _guard_self(admin, target, "停用")
        await _guard_last_admin(db, target, "停用")
    target.is_active = bool(data.is_active)
    revoked = 0
    if not data.is_active:
        revoked = await revoke_all_tokens(db, target.id)
    await db.commit()
    logger.info("管理员 %s 将 %s 置为 is_active=%s（踢下线 %d）",
                admin.id, target.id, data.is_active, revoked)
    return {"ok": True, "is_active": bool(target.is_active), "revoked_tokens": revoked}


@router.get("/users/{uid}/delete-preview")
async def delete_preview(uid: str, admin: User = Depends(require_admin),
                         db: AsyncSession = Depends(get_db)):
    """删除前先看清楚会删掉什么 —— 与真正的删除共用同一张步骤表。"""
    target = await _load_target(db, uid)
    blocked = None
    try:
        _guard_self(admin, target, "删除")
        await _guard_last_admin(db, target, "删除")
    except HTTPException as e:
        blocked = e.detail

    c = await _collect(db, uid)
    projects = (await db.execute(
        select(Project.id, Project.title, Project.visibility)
        .where(Project.user_id == uid))).all()
    return {
        "user": {"id": target.id, "username": target.username or "", "name": target.name},
        "counts": await _preview_counts(db, c),
        "projects": [{"id": pid, "title": t, "visibility": v or "private"}
                     for pid, t, v in projects],
        "blocked_reason": blocked,
    }


class DeleteIn(BaseModel):
    confirm_username: str


@router.post("/users/{uid}/delete")
async def delete_user(uid: str, data: DeleteIn, admin: User = Depends(require_admin),
                      db: AsyncSession = Depends(get_db)):
    """删除账号及其全部数据。**不可逆** —— 需要精确输入目标用户名做二次确认。"""
    target = await _load_target(db, uid)
    _guard_self(admin, target, "删除")
    await _guard_last_admin(db, target, "删除")

    typed = (data.confirm_username or "").strip()
    expect = (target.username or "").strip()
    if not expect:
        raise HTTPException(status_code=400, detail="该账号没有用户名，无法用用户名确认，请先设置用户名")
    if typed != expect:
        raise HTTPException(status_code=400, detail=f"确认失败：请准确输入用户名「{expect}」")

    c = await _collect(db, uid)
    counts = await _preview_counts(db, c)

    # 悬空指针：别人 fork 出来的副本是他们自己的仓库，保留；只清掉指向已删仓库的出处
    if c["project_ids"]:
        await db.execute(update(Project).where(Project.forked_from_id.in_(c["project_ids"]))
                         .values(forked_from_id=""))
        await db.execute(update(Project).where(Project.upstream_id.in_(c["project_ids"]))
                         .values(upstream_id=""))

    for _label, model, cond in _cascade_steps(c):
        await db.execute(delete(model).where(cond))

    unlinked = await _unlink_files(db, c)
    await db.commit()
    logger.warning("管理员 %s 删除了账号 %s（%s）: %s", admin.id, target.id, expect, counts)
    return {"ok": True, "deleted": counts, "unlinked_files": unlinked}
