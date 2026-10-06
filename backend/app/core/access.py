"""归属校验：多用户隔离的唯一入口。

未登录时回退 local_user —— 仅当 settings.allow_anonymous_local 为真（单机/开发）。
**公开部署必须把该项置 False**，否则匿名请求会拿到 local_user（即主人）的全部数据。

写操作 = 必须 owner（P5 协作者上线后放宽到 editor）；
读操作 = owner，或项目 visibility='public'（谁都能读，但不能改）。
"""
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Document, Project, User

LOCAL_USER_ID = "local_user"


def owner_id(user: User | None) -> str:
    """当前请求的归属用户 id。未登录时回退 local_user（仅开发/单机允许）。"""
    if user is not None:
        return user.id
    if not settings.allow_anonymous_local:
        raise HTTPException(status_code=401, detail="请先登录")
    return LOCAL_USER_ID


async def get_owned_project(db: AsyncSession, project_id: str, user: User | None,
                            write: bool = True) -> Project:
    """取项目并校验归属。"""
    p = await db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    if p.user_id == owner_id(user):
        return p
    if not write and (p.visibility or "private") == "public":
        return p
    raise HTTPException(status_code=403, detail="无权访问该项目")


async def get_readable_document(db: AsyncSession, document_id: str,
                                user: User | None) -> Document:
    """取文档并校验它所属项目的读权限（public 项目任何人可读）。"""
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if doc.project_id:
        await get_owned_project(db, doc.project_id, user, write=False)
    elif doc.user_id != owner_id(user):
        # 游离文档（不属于任何项目）：只有本人能读
        raise HTTPException(status_code=403, detail="无权访问该文档")
    return doc


async def get_writable_document(db: AsyncSession, document_id: str,
                                user: User | None) -> Document:
    """取文档并校验写权限：必须是自己名下的项目。"""
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if doc.project_id:
        await get_owned_project(db, doc.project_id, user, write=True)
    elif doc.user_id != owner_id(user):
        raise HTTPException(status_code=403, detail="无权修改该文档")
    return doc