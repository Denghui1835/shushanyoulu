"""书山有路 - Backend Configuration"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
# 项目根目录（backend 的上一层）
PROJECT_DIR = BASE_DIR.parent

# 数据目录：打包版通过环境变量 YQ_DATA_DIR 指向 exe 旁的 data/；开发默认 backend/data
DATA_DIR = Path(os.environ.get("YQ_DATA_DIR") or (BASE_DIR / "data"))


def _resolve_content_dir() -> Path:
    """手写课程卡内容库根目录（每学科一个子目录，每文件一张卡）。

    解析顺序：
      1. 环境变量 YQ_CONTENT_DIR（打包版 / 想把卡放外面时用）
      2. 项目根目录下 学习平台/内容库（开发默认）
      3. DATA_DIR/内容库（打包版兜底：把卡塞进 exe 旁的 data/）
    都不存在时返回 DATA_DIR/内容库 —— load_cards 会返回空、回退 LLM 生成，
    但会打日志，不再静默。
    """
    env = os.environ.get("YQ_CONTENT_DIR")
    if env:
        return Path(env)
    for candidate in (PROJECT_DIR / "学习平台" / "内容库", DATA_DIR / "内容库"):
        if candidate.is_dir():
            return candidate
    return DATA_DIR / "内容库"


CONTENT_DIR = _resolve_content_dir()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "书山有路 AI伴学"
    app_version: str = "0.1.0"
    debug: bool = True

    # Database — SQLite local-first (MVP)；打包版走 YQ_DATA_DIR
    database_url: str = f"sqlite+aiosqlite:///{(DATA_DIR / 'app.db').as_posix()}"

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
    document_dir: str = str(DATA_DIR / "documents")
    max_upload_size_mb: int = 100
    chunk_size_tokens: int = 1500  # target tokens per chunk

    # 微信开放平台 OAuth（小程序/公众号）
    wechat_app_id: str = ""
    wechat_app_secret: str = ""
    # 用户自有 API Key 加密密钥（fernet）；留空则每次启动随机生成（重启后旧 Key 失效）
    api_key_encrypt_secret: str = ""

    # 匿名回退到 local_user：开发/单机自用时为 True（未登录也能读写自己的书）。
    # **公开部署必须置 False**，否则未登录请求会拿到 local_user 名下（即主人）的全部数据。
    allow_anonymous_local: bool = True

    # AI 播客 / 通用 TTS
    # provider: edge（默认，免费免 Key）/ volc_mega（豆包大模型音色）/ volc_standard（豆包普通音色）/
    #           azure / mock（无声占位，纯链路测试用）
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
    podcast_audio_dir: str = str(DATA_DIR / "podcast_audio")

    # 作品社区：社区目录 JSON 的 URL（网盘/GitHub raw 直链），空则不启用社区列表
    community_catalog_url: str = ""
    # 项目 .yqp 导入上限（MB）：含文档 PDF，可大于普通上传上限
    max_project_import_mb: int = 2000

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]


settings = Settings()

# Ensure data directories exist
Path(settings.document_dir).mkdir(parents=True, exist_ok=True)
