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
    await _migrate_project_categories()
    await _ensure_ncre_course()
    await _ensure_ncre_c()
    await _migrate_legacy_user_api_keys()
    logger.info("Database initialized at %s", settings.database_url)


def _ensure_columns(conn):
    """SQLite 轻量迁移：为已有表补齐新增列（create_all 不会改已有表）。
    每个条目是 (列名, DDL)。DDL 可以是单条语句，也可以是语句元组——
    后者用于「加列 + 随附一次性数据回填」，只在列刚建时执行，不会重复跑。
    """
    for table, columns in _COLUMN_MIGRATIONS.items():
        cols = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
        for name, ddl in columns:
            if name not in cols:
                for stmt in ([ddl] if isinstance(ddl, str) else ddl):
                    conn.execute(text(stmt))
                logger.info("Migrated: added %s.%s", table, name)


# 各表的新增列迁移（SQLite ALTER TABLE ADD COLUMN）
_COLUMN_MIGRATIONS = {
    "documents": [
        ("project_id", "ALTER TABLE documents ADD COLUMN project_id VARCHAR(36)"),
        ("chapter_title", "ALTER TABLE documents ADD COLUMN chapter_title VARCHAR(256)"),
        ("sort_order", "ALTER TABLE documents ADD COLUMN sort_order INTEGER DEFAULT 0"),
        ("book_file_path", "ALTER TABLE documents ADD COLUMN book_file_path TEXT"),
        ("page_start", "ALTER TABLE documents ADD COLUMN page_start INTEGER"),
        ("page_end", "ALTER TABLE documents ADD COLUMN page_end INTEGER"),
        ("parent_id", "ALTER TABLE documents ADD COLUMN parent_id VARCHAR(36)"),
    ],
    "questions": [
        ("discarded", "ALTER TABLE questions ADD COLUMN discarded BOOLEAN DEFAULT 0"),
        ("in_mistake_book", "ALTER TABLE questions ADD COLUMN in_mistake_book BOOLEAN DEFAULT 0"),
        ("subtype", "ALTER TABLE questions ADD COLUMN subtype VARCHAR(16) DEFAULT ''"),
    ],
    "flashcards": [
        ("discarded", "ALTER TABLE flashcards ADD COLUMN discarded BOOLEAN DEFAULT 0"),
        ("visual", "ALTER TABLE flashcards ADD COLUMN visual TEXT DEFAULT ''"),
    ],
    "podcast_scripts": [
        ("prev_content", "ALTER TABLE podcast_scripts ADD COLUMN prev_content TEXT"),
        ("audio_seconds", "ALTER TABLE podcast_scripts ADD COLUMN audio_seconds INTEGER"),
    ],
    "users": [
        ("username", "ALTER TABLE users ADD COLUMN username VARCHAR(64)"),
        ("password_hash", "ALTER TABLE users ADD COLUMN password_hash VARCHAR(256) DEFAULT ''"),
        ("wechat_openid", "ALTER TABLE users ADD COLUMN wechat_openid VARCHAR(64)"),
        ("api_key_encrypted", "ALTER TABLE users ADD COLUMN api_key_encrypted TEXT"),
        ("api_base_url", "ALTER TABLE users ADD COLUMN api_base_url VARCHAR(256)"),
        ("api_model", "ALTER TABLE users ADD COLUMN api_model VARCHAR(128)"),
        ("last_project_id", "ALTER TABLE users ADD COLUMN last_project_id VARCHAR(36)"),
        ("last_project_title", "ALTER TABLE users ADD COLUMN last_project_title VARCHAR(128)"),
        ("last_subject", "ALTER TABLE users ADD COLUMN last_subject VARCHAR(64)"),
        ("last_topic", "ALTER TABLE users ADD COLUMN last_topic VARCHAR(128)"),
        ("last_activity_at", "ALTER TABLE users ADD COLUMN last_activity_at DATETIME"),
        # 管理员：回填既有库的「主人」= 认领了 local_user 行的那条（首个注册者）。
        # 全新安装时这里命中 0 行，改由 api/auth.py::register 的首个账号分支显式置位。
        ("is_admin", (
            "ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0",
            "UPDATE users SET is_admin=1 WHERE id='local_user'",
        )),
        # 停用/封禁：默认全部启用，既有行无需回填
        ("is_active", "ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1"),
    ],
    "projects": [
        ("is_public", "ALTER TABLE projects ADD COLUMN is_public BOOLEAN DEFAULT 0"),
        ("blank_enabled", "ALTER TABLE projects ADD COLUMN blank_enabled BOOLEAN DEFAULT 0"),
        ("kanban_enabled", "ALTER TABLE projects ADD COLUMN kanban_enabled BOOLEAN DEFAULT 0"),
        ("subject", "ALTER TABLE projects ADD COLUMN subject VARCHAR(64) DEFAULT ''"),
        ("category", "ALTER TABLE projects ADD COLUMN category VARCHAR(64) DEFAULT ''"),
        ("category_sub", "ALTER TABLE projects ADD COLUMN category_sub VARCHAR(64) DEFAULT ''"),
        ("learn_count", "ALTER TABLE projects ADD COLUMN learn_count INTEGER DEFAULT 0"),
        ("star_count", "ALTER TABLE projects ADD COLUMN star_count INTEGER DEFAULT 0"),
        ("fork_count", "ALTER TABLE projects ADD COLUMN fork_count INTEGER DEFAULT 0"),
        ("visibility", (
            "ALTER TABLE projects ADD COLUMN visibility VARCHAR(16) DEFAULT 'private'",
            # 回填：旧模型只有 is_public 布尔，公开的项目不能因为新列默认值而变私有
            "UPDATE projects SET visibility='public' WHERE is_public=1",
        )),
        ("license", "ALTER TABLE projects ADD COLUMN license VARCHAR(64) DEFAULT ''"),
        ("allow_fork", "ALTER TABLE projects ADD COLUMN allow_fork BOOLEAN DEFAULT 0"),
        ("forked_from_id", "ALTER TABLE projects ADD COLUMN forked_from_id VARCHAR(36) DEFAULT ''"),
        ("upstream_id", "ALTER TABLE projects ADD COLUMN upstream_id VARCHAR(36) DEFAULT ''"),
        ("is_shared", "ALTER TABLE projects ADD COLUMN is_shared BOOLEAN DEFAULT 0"),
    ],
    "schedule_slots": [
        ("notify_on_start", "ALTER TABLE schedule_slots ADD COLUMN notify_on_start BOOLEAN DEFAULT 0"),
        ("completed", "ALTER TABLE schedule_slots ADD COLUMN completed BOOLEAN DEFAULT 0"),
    ],
}


async def _migrate_project_categories():
    """旧数据迁移：把旧 subject 值归位到三级分类（门类/一级学科）。"""
    from app.core.categories import legacy_mapping
    from app.models import Project

    async with async_session() as db:
        projects = (await db.execute(
            select(Project).where(Project.category == "")
        )).scalars().all()
        changed = 0
        for p in projects:
            mapped = legacy_mapping(p.subject or "")
            if mapped:
                p.category, p.category_sub = mapped
                changed += 1
        if changed:
            await db.commit()
            logger.info("Migrated %d projects into 学科门类分类", changed)


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


async def _ensure_ncre_course():
    """种入「计算机二级 · Python」备考课程书（幂等，见 app.core.ncre_python）。"""
    from app.core.ncre_python import ensure_ncre_course

    await ensure_ncre_course()


async def _ensure_ncre_c():
    """种入「计算机二级 · C 语言」备考课程书（幂等，见 app.core.ncre_c）。"""
    from app.core.ncre_c import ensure_ncre_c

    await ensure_ncre_c()


def _guess_provider_from_url(base_url: str | None) -> str:
    """从旧的 api_base_url 猜服务商（旧的单 Key 时代只存了地址，没存服务商名）。"""
    url = (base_url or "").lower()
    if "dashscope" in url or "aliyuncs" in url:
        return "dashscope"
    if "moonshot" in url:
        return "moonshot"
    if "bigmodel" in url:
        return "zhipu"
    if "openai.com" in url:
        return "openai"
    if "deepseek" in url or not url:
        return "deepseek"
    return "custom"


async def _migrate_legacy_user_api_keys():
    """把旧的「单 Key 三元组」（users.api_key_encrypted/base_url/model）迁成 text 档。

    幂等：已有 text 档的用户直接跳过。旧列**保留不删**（SQLite 删列麻烦且无必要），
    只是此后不再写入。

    注意：旧版本没固定加密密钥（见 core/crypto.py），历史上存的密文很可能**已经解不开**。
    这种情况只记 warning 点名、不写行，让用户在个人中心重填 —— 不要假装迁移成功。
    """
    from app.core.crypto import decrypt_api_key, encrypt_secret
    from app.models import User, UserProviderConfig

    async with async_session() as db:
        users = (await db.execute(
            select(User).where(User.api_key_encrypted.is_not(None), User.api_key_encrypted != "")
        )).scalars().all()
        if not users:
            return

        have = set((await db.execute(
            select(UserProviderConfig.user_id).where(UserProviderConfig.capability == "text")
        )).scalars().all())

        migrated = 0
        for u in users:
            if u.id in have:
                continue
            plain = decrypt_api_key(u.api_key_encrypted or "")
            if not plain:
                logger.warning(
                    "用户 %s 的旧 API Key 无法解密（历史密钥未固定），需在个人中心重新填写", u.id)
                continue
            db.add(UserProviderConfig(
                user_id=u.id,
                capability="text",
                provider=_guess_provider_from_url(u.api_base_url),
                base_url=u.api_base_url,
                model=u.api_model or "deepseek-chat",
                secret_encrypted=encrypt_secret({"api_key": plain}),
                options_json="{}",
            ))
            migrated += 1

        if migrated:
            await db.commit()
            logger.info("迁移了 %d 个用户的旧 API Key 到 text 档", migrated)


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
