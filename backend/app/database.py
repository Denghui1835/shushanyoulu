"""SQLAlchemy async database setup — SQLite local-first (MVP)."""
import logging

from sqlalchemy import event, text, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger("yuanqi.db")

engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args={"timeout": 30},
)

@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    dbapi_connection.execute("PRAGMA journal_mode=WAL;")
    dbapi_connection.execute("PRAGMA busy_timeout=5000;")
    dbapi_connection.execute("PRAGMA foreign_keys=ON;")

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Create all tables (MVP: skip Alembic, use metadata.create_all)."""
    from app import models  # noqa: F401  ensure models are imported/registered

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_columns)
    await _ensure_default_project()
    logger.info("Database initialized at %s", settings.database_url)


def _ensure_columns(conn):
    """SQLite 轻量迁移：为已有 documents 表补齐书架相关列（create_all 不会改已有表）。"""
    cols = {row[1] for row in conn.execute(text("PRAGMA table_info(documents)"))}
    for name, ddl in (
        ("project_id", "ALTER TABLE documents ADD COLUMN project_id VARCHAR(36)"),
        ("chapter_title", "ALTER TABLE documents ADD COLUMN chapter_title VARCHAR(256)"),
        ("sort_order", "ALTER TABLE documents ADD COLUMN sort_order INTEGER DEFAULT 0"),
        ("book_file_path", "ALTER TABLE documents ADD COLUMN book_file_path TEXT"),
        ("page_start", "ALTER TABLE documents ADD COLUMN page_start INTEGER"),
        ("page_end", "ALTER TABLE documents ADD COLUMN page_end INTEGER"),
        ("parent_id", "ALTER TABLE documents ADD COLUMN parent_id VARCHAR(36)"),
    ):
        if name not in cols:
            conn.execute(text(ddl))
            logger.info("Migrated: added documents.%s", name)


async def ensure_default_project(db: AsyncSession):
    """确保「未分类」项目存在并返回它（不存在则创建）。"""
    from app.models import Project

    proj = (await db.execute(select(Project).where(Project.title == "未分类"))).scalars().first()
    if proj is None:
        proj = Project(user_id="local_user", title="未分类",
                       description="未归入项目的文档", icon="🗂️")
        db.add(proj)
        await db.flush()
    return proj


async def _ensure_default_project():
    """旧数据迁移：无归属文档自动归入「未分类」默认项目（仅在存在无归属文档时创建）。"""
    from app.models import Document

    async with async_session() as db:
        orphan = (await db.execute(select(Document).where(Document.project_id.is_(None)).limit(1))).scalars().first()
        if orphan is None:
            return
        proj = await ensure_default_project(db)
        orphans = (await db.execute(select(Document).where(Document.project_id.is_(None)))).scalars().all()
        for d in orphans:
            d.project_id = proj.id
        await db.commit()
        logger.info("Migrated %d orphan documents into project「%s」", len(orphans), proj.title)
