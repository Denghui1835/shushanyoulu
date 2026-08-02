"""元气搭子 AI伴学 — FastAPI 应用入口."""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("yuanqi")


async def startup_init():
    await init_db()

    # Load .env file for API config (project .env takes priority over shell env)
    env_vals = {}
    env_path = Path(__file__).resolve().parent.parent / ".env"
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    await startup_init()
    yield


app = FastAPI(
    title="元气搭子 API",
    description="元气搭子 - AI 主动伴学，让学习有人陪伴",
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

from app.api.companion import router as companion_router
from app.api.documents import router as documents_router
from app.api.projects import router as projects_router
from app.api.knowledge import router as knowledge_router
from app.api.questions import router as questions_router
from app.api.flashcards import router as flashcards_router
from app.api.pipeline import router as pipeline_router
from app.api.study import router as study_router
from app.api.reading import router as reading_router
from app.api.podcast import router as podcast_router
from app.api.community import router as community_router

app.include_router(companion_router)
app.include_router(documents_router)
app.include_router(projects_router)
app.include_router(knowledge_router)
app.include_router(questions_router)
app.include_router(flashcards_router)
app.include_router(pipeline_router)
app.include_router(study_router)
app.include_router(reading_router)
app.include_router(podcast_router)
app.include_router(community_router)


@app.get("/")
async def root():
    return {"name": "元气搭子 AI伴学", "version": settings.app_version, "status": "running", "docs": "/docs"}


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=settings.debug)
