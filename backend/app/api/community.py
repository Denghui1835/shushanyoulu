"""作品社区 API：浏览社区目录（共享 JSON），一键下载并导入 .yqp 项目。

社区形态：文件导出/导入。把 .yqp 放到共享位置（网盘/GitHub 仓库），
在 backend/.env 配置 COMMUNITY_CATALOG_URL 指向一个 catalog.json：
{"items": [{"title", "description", "author", "icon", "file_url", "updated_at"}]}
"""
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.core.project_package import import_project

logger = logging.getLogger("yuanqi.api.community")
router = APIRouter(prefix="/api/community", tags=["community"])


@router.get("/catalog")
async def get_catalog(db: AsyncSession = Depends(get_db)):
    """拉取社区目录。未配置 URL 时返回 configured=False 并给提示。"""
    url = (settings.community_catalog_url or "").strip()
    if not url:
        return {"configured": False, "items": [], "message":
                "未配置社区目录。在 backend/.env 设置 COMMUNITY_CATALOG_URL，指向你的 catalog.json"}
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            resp = await c.get(url)
            resp.raise_for_status()
            data = resp.json()
        items = data.get("items", []) if isinstance(data, dict) else data
        return {"configured": True, "items": items if isinstance(items, list) else [], "message": ""}
    except Exception as e:
        logger.warning("社区目录加载失败: %s", e)
        return {"configured": True, "items": [], "message": f"目录加载失败：{str(e)[:100]}"}


@router.post("/import")
async def community_import(url: str, db: AsyncSession = Depends(get_db)):
    """从社区 URL 下载 .yqp 并导入为项目。"""
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL 无效")
    try:
        async with httpx.AsyncClient(timeout=180) as c:
            resp = await c.get(url)
            if resp.status_code != 200:
                raise HTTPException(status_code=400,
                                    detail=f"下载失败：HTTP {resp.status_code}")
            content = resp.content
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"下载失败：{str(e)[:100]}")

    try:
        p = await import_project(db, content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("社区导入失败")
        raise HTTPException(status_code=500, detail=f"导入失败：{str(e)[:200]}")
    return {"id": p.id, "title": p.title, "description": p.description,
            "icon": p.icon, "document_count": 0, "created_at": p.created_at.isoformat()}
