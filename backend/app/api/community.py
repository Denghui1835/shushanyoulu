"""作品社区 API：项目发布、广场浏览、一键学习（往智谱「公开项目广场」靠拢）。

- 发布/取消发布：把「我拥有的项目」设为公开/私有（需登录，校验归属）。
- 广场：浏览所有用户公开的项目（无需登录）。
- 一键学习：把别人的公开项目复制一份到自己的书架（需登录，服务端直接复制，不走文件）。

旧的文件目录版（catalog.json）已由广场取代，.yqp 导出/导入保留作备份/离线分享（见 api/projects.py）。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.auth import get_current_user
from app.core.project_package import export_project, import_project
from app.models import Project, Document, User

logger = logging.getLogger("yuanqi.api.community")
router = APIRouter(prefix="/api/community", tags=["community"])


# ---------------------------------------------------------------- 发布 / 取消发布

async def _owned_project(db: AsyncSession, project_id: str, user: User) -> Project:
    p = await db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    if p.user_id != user.id:
        raise HTTPException(status_code=403, detail="只能操作自己拥有的项目")
    return p


@router.post("/projects/{project_id}/publish")
async def publish_project(project_id: str, user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    """发布项目到广场（公开）。"""
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


# ---------------------------------------------------------------- 广场

@router.get("/plaza")
async def plaza(db: AsyncSession = Depends(get_db)):
    """广场：所有公开项目（含作者名、章节数）。"""
    rows = (await db.execute(
        select(Project, User.username)
        .join(User, Project.user_id == User.id)
        .where(Project.is_public == True)  # noqa: E712
        .order_by(Project.created_at.desc())
    )).all()
    doc_counts = dict((await db.execute(
        select(Document.project_id, func.count())
        .where(Document.project_id.is_not(None), Document.content_type != "group")
        .group_by(Document.project_id)
    )).all())
    items = []
    for p, username in rows:
        items.append({
            "id": p.id, "title": p.title, "description": p.description,
            "icon": p.icon, "author": username or "匿名",
            "chapter_count": int(doc_counts.get(p.id, 0)),
            "created_at": p.created_at.isoformat(),
        })
    return {"count": len(items), "items": items}


# ---------------------------------------------------------------- 一键学习

@router.post("/plaza/{project_id}/learn")
async def learn_project(project_id: str, user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    """一键学习：把别人的公开项目复制一份到自己的书架（服务端复制）。"""
    src = await db.get(Project, project_id)
    if not src or not src.is_public:
        raise HTTPException(status_code=404, detail="项目不存在或未公开")
    if src.user_id == user.id:
        raise HTTPException(status_code=400, detail="这是你自己的项目，无需学习")
    try:
        content = await export_project(db, project_id)
        new_p = await import_project(db, content, owner_id=user.id,
                                     title_override=f"{src.title}（已学习）")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("一键学习失败 project=%s", project_id)
        raise HTTPException(status_code=500, detail=f"学习失败：{str(e)[:200]}")
    return {"id": new_p.id, "title": new_p.title, "icon": new_p.icon}
