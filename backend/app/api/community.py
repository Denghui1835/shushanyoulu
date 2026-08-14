"""作品社区 API — 番茄小说生态 + GitHub 协作机制.

核心：
- 广场：搜索 + 学科分类 + 热门/最新榜单 + 课程卡片流（含学习/收藏/Fork 统计）
- 收藏（star）：像 GitHub star / 番茄收藏
- Fork：复制一份课程到自己空间（可自由修改）
- 修改建议：对别人的课程提改进建议（类似 GitHub issue/PR），作者可采纳/拒绝/标记已应用
- 一键学习：把课程复制进自己的书架
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.auth import get_current_user
from app.core.project_package import export_project, import_project
from app.core.categories import category_tree, normalize_category
from app.models import Project, Document, User, ProjectStar, ProjectFork, ProjectSuggestion

logger = logging.getLogger("yuanqi.api.community")
router = APIRouter(prefix="/api/community", tags=["community"])


# ---------------------------------------------------------------- helpers

async def _owned_project(db: AsyncSession, project_id: str, user: User) -> Project:
    p = await db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    if p.user_id != user.id:
        raise HTTPException(status_code=403, detail="只能操作自己拥有的项目")
    return p


async def _public_project(db: AsyncSession, project_id: str) -> Project:
    p = await db.get(Project, project_id)
    if not p or not p.is_public:
        raise HTTPException(status_code=404, detail="课程不存在或未公开")
    return p


async def _chapter_count(db: AsyncSession, project_id: str) -> int:
    return int((await db.execute(
        select(func.count()).select_from(Document).where(
            Document.project_id == project_id,
            Document.project_id.is_not(None),
            Document.content_type != "group",
        )
    )).scalar() or 0)


def _card(p: Project, author: str, chapter_count: int) -> dict:
    # 分类显示：门类 / 一级学科（旧 subject 作为兜底）
    category = p.category or ""
    category_sub = p.category_sub or ""
    if not category and p.subject:
        mapped = legacy_map(p.subject)
        if mapped:
            category, category_sub = mapped
    return {
        "id": p.id, "title": p.title, "description": p.description,
        "icon": p.icon,
        "subject": p.subject or (category_sub or category or "未分类"),
        "category": category,
        "category_sub": category_sub,
        "category_label": f"{category} · {category_sub}" if category else "未分类",
        "author": author or "匿名",
        "chapter_count": chapter_count,
        "learn_count": int(p.learn_count or 0),
        "star_count": int(p.star_count or 0),
        "fork_count": int(p.fork_count or 0),
        "created_at": p.created_at.isoformat(),
    }


def legacy_map(subject: str) -> tuple[str, str] | None:
    """旧 subject → (门类, 一级学科)。"""
    from app.core.categories import legacy_mapping
    return legacy_mapping(subject)


# ---------------------------------------------------------------- 发布 / 取消发布

@router.post("/projects/{project_id}/publish")
async def publish_project(project_id: str, user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    """发布课程到广场（公开）。"""
    p = await _owned_project(db, project_id, user)
    p.is_public = True
    await db.commit()
    return {"ok": True, "is_public": True}


@router.post("/projects/{project_id}/unpublish")
async def unpublish_project(project_id: str, user: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    """取消发布（私有）。"""
    p = await _owned_project(db, project_id, user)
    p.is_public = False
    await db.commit()
    return {"ok": True, "is_public": False}


@router.patch("/projects/{project_id}")
async def patch_project(project_id: str, body: dict, user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    """作者更新课程信息（标题/简介/图标/学科门类分类）。"""
    p = await _owned_project(db, project_id, user)
    for k in ("title", "description", "icon", "subject"):
        if k in body and body[k] is not None:
            setattr(p, k, str(body[k])[:256])
    # 三级分类：门类 + 一级学科（带规整）
    if "category" in body or "category_sub" in body:
        cat, sub = normalize_category(
            body.get("category"), body.get("category_sub"),
            fallback_subject=p.subject or "")
        p.category = cat
        p.category_sub = sub
        if not p.subject:
            p.subject = sub or cat
    await db.commit()
    return {"ok": True, "id": p.id}


# ---------------------------------------------------------------- 广场

@router.get("/categories")
async def categories():
    """学科分类树：门类 → 一级学科（三级分类的前两级）。"""
    return category_tree()


@router.get("/plaza")
async def plaza(search: str = "", subject: str = "", sort: str = "new",
                category: str = "", category_sub: str = "",
                db: AsyncSession = Depends(get_db)):
    """广场：所有公开课程，支持搜索 / 学科门类分类 / 榜单排序。"""
    q = select(Project, User.username).join(User, Project.user_id == User.id).where(
        Project.is_public == True)  # noqa: E712
    if search.strip():
        like = f"%{search.strip()}%"
        q = q.where(or_(Project.title.like(like), Project.description.like(like)))
    if category.strip():
        q = q.where(Project.category == category.strip())
        if category_sub.strip():
            q = q.where(Project.category_sub == category_sub.strip())
    elif subject.strip() and subject != "全部":
        # 兼容旧的 subject 过滤（旧数据归位前仍能按 subject 筛）
        q = q.where(or_(Project.subject == subject.strip(),
                        Project.category_sub == subject.strip()))
    if sort == "hot":
        q = q.order_by((Project.learn_count + Project.star_count + Project.fork_count).desc())
    else:
        q = q.order_by(Project.created_at.desc())

    rows = (await db.execute(q)).all()
    items = []
    for p, username in rows:
        items.append(_card(p, username or "匿名", await _chapter_count(db, p.id)))
    return {"count": len(items), "items": items}


@router.get("/plaza/{project_id}")
async def plaza_detail(project_id: str, db: AsyncSession = Depends(get_db)):
    """课程详情页数据：完整信息 + 章节/知识点 + 建议列表。"""
    p = await _public_project(db, project_id)
    author = (await db.get(User, p.user_id)) or None
    chapters = (await db.execute(
        select(Document).where(Document.project_id == project_id,
                               Document.project_id.is_not(None),
                               Document.content_type != "group")
        .order_by(Document.sort_order)
    )).scalars().all()
    suggestions = (await db.execute(
        select(ProjectSuggestion).where(ProjectSuggestion.project_id == project_id)
        .order_by(ProjectSuggestion.created_at.desc()).limit(50)
    )).scalars().all()
    return {
        "course": _card(p, author.username if author else "匿名", len(chapters)),
        "chapters": [{"id": c.id, "title": c.title} for c in chapters],
        "suggestions": [{
            "id": s.id, "username": s.username, "content": s.content,
            "status": s.status, "created_at": s.created_at.isoformat(),
        } for s in suggestions],
    }


# ---------------------------------------------------------------- 收藏 star

@router.post("/plaza/{project_id}/star")
async def star_project(project_id: str, user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    await _public_project(db, project_id)
    exists = (await db.execute(
        select(ProjectStar).where(ProjectStar.project_id == project_id,
                                  ProjectStar.user_id == user.id)
    )).scalars().first()
    if exists:
        return {"ok": True, "starred": True}
    db.add(ProjectStar(project_id=project_id, user_id=user.id))
    p = await db.get(Project, project_id)
    p.star_count = int(p.star_count or 0) + 1
    await db.commit()
    return {"ok": True, "starred": True, "star_count": p.star_count}


@router.post("/plaza/{project_id}/unstar")
async def unstar_project(project_id: str, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    row = (await db.execute(
        select(ProjectStar).where(ProjectStar.project_id == project_id,
                                  ProjectStar.user_id == user.id)
    )).scalars().first()
    if row:
        await db.delete(row)
        p = await db.get(Project, project_id)
        if p:
            p.star_count = max(0, int(p.star_count or 0) - 1)
        await db.commit()
    return {"ok": True, "starred": False}


# ---------------------------------------------------------------- Fork

@router.post("/plaza/{project_id}/fork")
async def fork_project(project_id: str, user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    """Fork：复制一份课程到自己的空间，可自由修改（GitHub fork）。"""
    src = await _public_project(db, project_id)
    if src.user_id == user.id:
        raise HTTPException(status_code=400, detail="这是你自己的课程，无需 Fork")
    try:
        content = await export_project(db, project_id)
        new_p = await import_project(db, content, owner_id=user.id,
                                     title_override=f"{src.title}（Fork）")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Fork 失败 project=%s", project_id)
        raise HTTPException(status_code=500, detail=f"Fork 失败：{str(e)[:200]}")
    db.add(ProjectFork(from_project_id=src.id, new_project_id=new_p.id, user_id=user.id))
    src.fork_count = int(src.fork_count or 0) + 1
    await db.commit()
    return {"id": new_p.id, "title": new_p.title, "icon": new_p.icon}


# ---------------------------------------------------------------- 一键学习

@router.post("/plaza/{project_id}/learn")
async def learn_project(project_id: str, user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    """一键学习：把别人的公开课程复制一份到自己的书架（学习数 +1）。"""
    src = await _public_project(db, project_id)
    if src.user_id == user.id:
        raise HTTPException(status_code=400, detail="这是你自己的课程，无需学习")
    content = await export_project(db, project_id)
    new_p = await import_project(db, content, owner_id=user.id,
                                 title_override=f"{src.title}（已学习）")
    src.learn_count = int(src.learn_count or 0) + 1
    await db.commit()
    return {"id": new_p.id, "title": new_p.title, "icon": new_p.icon}


# ---------------------------------------------------------------- 修改建议（GitHub PR/issue 式）

@router.get("/plaza/{project_id}/suggestions")
async def list_suggestions(project_id: str, db: AsyncSession = Depends(get_db)):
    """课程的建议列表（公开可看）。"""
    rows = (await db.execute(
        select(ProjectSuggestion).where(ProjectSuggestion.project_id == project_id)
        .order_by(ProjectSuggestion.created_at.desc()).limit(100)
    )).scalars().all()
    return [{
        "id": s.id, "username": s.username, "content": s.content,
        "status": s.status, "created_at": s.created_at.isoformat(),
    } for s in rows]


@router.post("/plaza/{project_id}/suggestions")
async def create_suggestion(project_id: str, body: dict,
                            user: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    """对别人的课程提修改建议。"""
    await _public_project(db, project_id)
    content = (body.get("content") or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="建议内容不能为空")
    if len(content) > 2000:
        raise HTTPException(status_code=400, detail="建议太长了，压缩到 2000 字以内")
    s = ProjectSuggestion(project_id=project_id, user_id=user.id,
                          username=user.name or user.username or "匿名",
                          content=content)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return {"ok": True, "id": s.id, "username": s.username,
            "content": s.content, "status": s.status,
            "created_at": s.created_at.isoformat()}


async def _owned_suggestion(db: AsyncSession, project_id: str, sid: str, user: User):
    """作者操作自己课程下的建议（先校验课程归属）。"""
    await _owned_project(db, project_id, user)
    s = await db.get(ProjectSuggestion, sid)
    if not s or s.project_id != project_id:
        raise HTTPException(status_code=404, detail="建议不存在")
    return s


@router.post("/projects/{project_id}/suggestions/{sid}/accept")
async def accept_suggestion(project_id: str, sid: str, user: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    s = await _owned_suggestion(db, project_id, sid, user)
    s.status = "accepted"
    await db.commit()
    return {"ok": True, "status": "accepted"}


@router.post("/projects/{project_id}/suggestions/{sid}/applied")
async def apply_suggestion(project_id: str, sid: str, user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    """作者采纳并已应用该建议。"""
    s = await _owned_suggestion(db, project_id, sid, user)
    s.status = "applied"
    await db.commit()
    return {"ok": True, "status": "applied"}


@router.post("/projects/{project_id}/suggestions/{sid}/reject")
async def reject_suggestion(project_id: str, sid: str, user: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    s = await _owned_suggestion(db, project_id, sid, user)
    s.status = "rejected"
    await db.commit()
    return {"ok": True, "status": "rejected"}
