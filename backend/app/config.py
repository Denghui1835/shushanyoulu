"""元气搭子 - Backend Configuration"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "元气搭子 AI伴学"
    app_version: str = "0.1.0"
    debug: bool = True

    # Database — SQLite local-first (MVP)
    database_url: str = "sqlite+aiosqlite:///./data/app.db"

    # LLM
    default_model: str = "deepseek-chat"
    default_temperature: float = 0.7
    default_max_tokens: int = 4096
    cache_ttl_days: int = 30
    max_retries: int = 2
    request_timeout: int = 120
    max_concurrent_requests: int = 5
    daily_token_limit: int = 1_000_000

    # File Storage
    document_dir: str = str(BASE_DIR / "data" / "documents")
    max_upload_size_mb: int = 100
    chunk_size_tokens: int = 1500  # target tokens per chunk

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]


settings = Settings()

# Ensure data directories exist
Path(settings.document_dir).mkdir(parents=True, exist_ok=True)
