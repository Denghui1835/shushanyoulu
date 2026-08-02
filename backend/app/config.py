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

    # AI 播客（TTS）
    # provider: edge（默认，免费免 Key）/ volc（火山引擎/豆包）/ azure / mock（无声占位，纯链路测试用）
    # edge = 开源 edge-tts 包（rany2/edge-tts），走微软 Edge 在线神经语音，无需注册付费
    tts_provider: str = "edge"
    # --- edge-tts（免费）---
    edge_tts_voice_a: str = "zh-CN-XiaoxiaoNeural"  # 主播A 女声（晓晓）
    edge_tts_voice_b: str = "zh-CN-YunxiNeural"     # 主播B 男声（云希）
    # --- 火山引擎/字节豆包 TTS（可选，付费）---
    volc_app_id: str = ""
    volc_access_token: str = ""
    volc_tts_cluster: str = "volcano_mega"   # 大模型音色集群；普通音色用 volcano_tts
    volc_tts_voice_a: str = "BV001_streaming"  # 主播A 女声（灿灿）
    volc_tts_voice_b: str = "BV700_streaming"  # 主播B 男声（辉晓）
    # --- Azure 认知服务 TTS（可选，付费）---
    azure_tts_key: str = ""
    azure_tts_region: str = "eastasia"
    azure_tts_voice_a: str = "zh-CN-XiaoxiaoNeural"
    azure_tts_voice_b: str = "zh-CN-YunxiNeural"
    podcast_audio_dir: str = str(BASE_DIR / "data" / "podcast_audio")

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]


settings = Settings()

# Ensure data directories exist
Path(settings.document_dir).mkdir(parents=True, exist_ok=True)
