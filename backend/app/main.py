"""书山有路 AI伴学 — FastAPI 应用入口."""
import logging
import mimetypes
import os
from contextlib import asynccontextmanager
from pathlib import Path

# Windows 的 mimetypes 常缺 .js/.mjs 等注册，导致 <script type="module"> 被按 text/plain 返回 → 页面空白
for _ext, _mime in ((".js", "text/javascript"), (".mjs", "text/javascript"),
                    (".css", "text/css"), (".json", "application/json"),
                    (".svg", "image/svg+xml"), (".woff2", "font/woff2"),
                    (".wasm", "application/wasm"), (".map", "application/json")):
    mimetypes.add_type(_mime, _ext)

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from app.config import settings, DATA_DIR
from app.database import init_db, async_session
from app.core.api_scheduler.client import set_current_user_id
from app.core.api_scheduler import api_client
from app.models import AuthToken, User

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("yuanqi")


async def startup_init():
    await init_db()

    # Load .env file for API config（打包版从数据目录读，开发读 backend/.env）
    env_vals = {}
    for env_path in (DATA_DIR / ".env", Path(__file__).resolve().parent.parent / ".env"):
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env_vals[k.strip()] = v.strip().strip('"').strip("'")

    # 项目 .env 的 DeepSeek Key 优先；其次 shell 环境的 DEEPSEEK；最后才是 ANTHROPIC
    # （注意：宿主 shell 可能带有 Claude Code 的 ANTHROPIC_AUTH_TOKEN，不能让它顶掉项目的 DeepSeek 配置）
    if env_vals.get("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_API_KEY"):
        from app.core.api_scheduler import api_client
        api_key = env_vals.get("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
        api_client.configure_adapter(
            "deepseek", api_key,
            base_url="https://api.deepseek.com/v1", model_name=settings.default_model,
        )
        logger.info("LLM adapter configured: deepseek (%s)", settings.default_model)
    elif env_vals.get("ANTHROPIC_AUTH_TOKEN") or os.getenv("ANTHROPIC_AUTH_TOKEN"):
        from app.core.api_scheduler import api_client
        api_key = env_vals.get("ANTHROPIC_AUTH_TOKEN") or os.getenv("ANTHROPIC_AUTH_TOKEN")
        base = env_vals.get("ANTHROPIC_BASE_URL") or os.getenv("ANTHROPIC_BASE_URL") or "https://api.anthropic.com/v1"
        model = env_vals.get("ANTHROPIC_MODEL") or os.getenv("ANTHROPIC_MODEL") or "claude-sonnet-4-5"
        api_client.configure_adapter("anthropic", api_key, base_url=base, model_name=model)
        logger.info("LLM adapter configured: anthropic (%s)", model)
    else:
        logger.warning("未配置 API Key，请在 backend/.env 设置 DEEPSEEK_API_KEY")

    # 放在全局适配器之后：注册表里全局键必须排在前面，全局回退才稳。
    # 不跑这一步，用户重启后自有 Key 会静默失效、偷偷跑服务器的额度。
    from app.core.provider_config import reload_user_adapters
    await reload_user_adapters()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await startup_init()
    yield


app = FastAPI(
    title="书山有路 API",
    description="书山有路 - AI 主动伴学，让学习有人陪伴",
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def set_user_llm_context(request: Request, call_next):
    """已登录且配置了自有服务商的用户 → 本次请求的 LLM 调用用其适配器（开源免费：用户自理 Key 费用）。"""
    try:
        header = request.headers.get("authorization", "")
        if header.lower().startswith("bearer "):
            token = header[7:].strip()
            if token:
                async with async_session() as db:
                    row = (await db.execute(
                        select(AuthToken).where(AuthToken.token == token)
                    )).scalars().first()
                    if row:
                        u = await db.get(User, row.user_id)
                        # 判据是「内存注册表里真有他的适配器」，而不是「库里有没有密文」：
                        # 密文在但解不开（换过加密密钥）时，前者才如实反映可用性。
                        if u and u.is_active and api_client.has_any_user_adapter(u.id):
                            set_current_user_id(u.id)
    except Exception:
        pass
    try:
        return await call_next(request)
    finally:
        set_current_user_id("local_user")

from app.api.companion import router as companion_router
from app.api.lesson import router as lesson_router
from app.api.documents import router as documents_router
from app.api.projects import router as projects_router
from app.api.knowledge import router as knowledge_router
from app.api.questions import router as questions_router
from app.api.flashcards import router as flashcards_router
from app.api.pipeline import router as pipeline_router
from app.api.study import router as study_router
from app.api.reading import router as reading_router
from app.api.podcast import router as podcast_router
from app.api.listen import router as listen_router
from app.api.community import router as community_router
from app.api.auth import router as auth_router
from app.api.profile import router as profile_router
from app.api.tts import router as tts_router
from app.api.stats import router as stats_router
from app.api.kanban import router as kanban_router
from app.api.schedules import router as schedules_router
from app.api.course import router as course_router
from app.api.social import router as social_router
from app.api.system import router as system_router
from app.api.admin import router as admin_router

app.include_router(companion_router)
app.include_router(lesson_router)
app.include_router(documents_router)
app.include_router(projects_router)
app.include_router(knowledge_router)
app.include_router(questions_router)
app.include_router(flashcards_router)
app.include_router(pipeline_router)
app.include_router(study_router)
app.include_router(reading_router)
app.include_router(podcast_router)
app.include_router(listen_router)
app.include_router(community_router)
app.include_router(auth_router)
app.include_router(profile_router)
app.include_router(tts_router)
app.include_router(stats_router)
app.include_router(kanban_router)
app.include_router(schedules_router)
app.include_router(course_router)
app.include_router(social_router)
app.include_router(system_router)
app.include_router(admin_router)


@app.get("/")
async def root():
    if DIST_DIR and (DIST_DIR / "index.html").exists():
        return FileResponse(DIST_DIR / "index.html")
    return {"name": "书山有路 AI伴学", "version": settings.app_version, "status": "running", "docs": "/docs"}


@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------- 前端静态托管（打包版/生产）
# 打包版（PyInstaller）把 frontend/dist 作为数据打进 _MEIPASS/dist；开发读 ../frontend/dist
def _resolve_dist() -> Path | None:
    import sys
    if getattr(sys, "frozen", False):
        cand = Path(sys._MEIPASS) / "dist"   # 打包版：内置前端
    else:
        cand = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"  # 开发：仓库前端构建产物
    return cand if cand.is_dir() else None


DIST_DIR = _resolve_dist()

if DIST_DIR:
    if (DIST_DIR / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        """SPA 兜底：非 /api 的路径都返回前端 index.html（React Router 深链）。"""
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        if path:
            f = DIST_DIR / path
            if f.is_file():
                return FileResponse(f)
        return FileResponse(DIST_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn
    # 0.0.0.0 = 允许局域网/手机访问（移动端连接后端必需）；如只想本机访问可设 host=127.0.0.1
    host = os.environ.get("YQ_HOST", "0.0.0.0")
    uvicorn.run("app.main:app", host=host, port=8000, reload=settings.debug)
