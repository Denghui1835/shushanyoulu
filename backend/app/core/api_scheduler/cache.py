"""API response cache with SHA256-based keys"""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import async_session
from app.models import APICache


def compute_cache_key(
    content: str,
    prompt_template_id: str,
    model_name: str,
    config_hash: str = "",
) -> str:
    """Compute deterministic cache key from input parameters."""
    normalized = "".join(content.split()).lower().encode("utf-8")
    seed = normalized + prompt_template_id.encode() + model_name.encode() + config_hash.encode()
    return hashlib.sha256(seed).hexdigest()


def compute_config_hash(temperature: float, top_p: float, max_tokens: int) -> str:
    """Hash generation config for cache key."""
    return hashlib.sha256(f"{temperature}:{top_p}:{max_tokens}".encode()).hexdigest()[:16]


class APICacheManager:
    """Manages API response caching with SQLite backend"""

    def __init__(self):
        self._session: AsyncSession | None = None

    async def _get_session(self) -> AsyncSession:
        async with async_session() as session:
            return session

    async def get(self, cache_key: str) -> str | None:
        """Retrieve cached response. Returns None if not found or expired."""
        async with async_session() as session:
            result = await session.execute(
                select(APICache).where(APICache.cache_key == cache_key)
            )
            entry = result.scalar_one_or_none()
            if entry is None:
                return None
            # Check TTL
            age = datetime.now(timezone.utc).replace(tzinfo=None) - entry.created_at
            if age > timedelta(days=entry.ttl_days):
                await session.delete(entry)
                await session.commit()
                return None
            return entry.response_content

    async def set(
        self,
        cache_key: str,
        response_content: str,
        model_used: str,
        tokens_input: int,
        tokens_output: int,
        ttl_days: int = 30,
    ):
        """Store a response in cache."""
        async with async_session() as session:
            entry = APICache(
                cache_key=cache_key,
                response_content=response_content,
                model_used=model_used,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                ttl_days=ttl_days,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            await session.merge(entry)
            await session.commit()

    async def delete(self, cache_key: str):
        """Remove a cache entry."""
        async with async_session() as session:
            await session.execute(
                delete(APICache).where(APICache.cache_key == cache_key)
            )
            await session.commit()

    async def stats(self) -> dict:
        """Get cache statistics."""
        async with async_session() as session:
            result = await session.execute(select(APICache))
            entries = result.scalars().all()
            total = len(entries)
            total_tokens_saved = sum(e.tokens_output or 0 for e in entries)
            return {
                "total_entries": total,
                "total_tokens_saved": total_tokens_saved,
            }


cache_manager = APICacheManager()
