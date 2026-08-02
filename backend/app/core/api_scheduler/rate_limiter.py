"""Rate limiter and quota management"""
import asyncio
from datetime import date, datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import async_session
from app.models import APIQuota
from app.config import settings


class RateLimiter:
    """Controls API call rate and quota per user"""

    def __init__(self):
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_requests)
        self._daily_limits: dict[str, int] = {}

    async def acquire(self, user_id: str = "local_user") -> bool:
        """Acquire a concurrency slot. Returns True if acquired."""
        return await self._semaphore.acquire()

    def release(self):
        """Release a concurrency slot."""
        self._semaphore.release()

    async def check_quota(self, user_id: str, estimated_tokens: int) -> tuple[bool, str]:
        """Check if user has enough daily quota. Returns (allowed, message)."""
        async with async_session() as session:
            result = await session.execute(
                select(APIQuota).where(APIQuota.user_id == user_id)
            )
            quota = result.scalar_one_or_none()

            if quota is None:
                # First use, create quota entry
                quota = APIQuota(
                    user_id=user_id,
                    daily_limit=settings.daily_token_limit,
                    used_today=0,
                    reset_at=date.today(),
                )
                session.add(quota)
                await session.commit()
                return True, "ok"

            # Reset if it's a new day
            if quota.reset_at != date.today():
                quota.used_today = 0
                quota.reset_at = date.today()

            if quota.used_today + estimated_tokens > quota.daily_limit:
                return False, f"Daily token limit reached: {quota.used_today}/{quota.daily_limit}"

            return True, "ok"

    async def record_usage(
        self, user_id: str, tokens_input: int, tokens_output: int
    ):
        """Record token usage against quota."""
        async with async_session() as session:
            result = await session.execute(
                select(APIQuota).where(APIQuota.user_id == user_id)
            )
            quota = result.scalar_one_or_none()
            if quota:
                if quota.reset_at != date.today():
                    quota.used_today = 0
                    quota.reset_at = date.today()
                quota.used_today += (tokens_input + tokens_output)
                quota.total_used += (tokens_input + tokens_output)
                await session.commit()

    async def get_quota_status(self, user_id: str) -> dict:
        """Get current quota status for a user."""
        async with async_session() as session:
            result = await session.execute(
                select(APIQuota).where(APIQuota.user_id == user_id)
            )
            quota = result.scalar_one_or_none()
            if quota is None:
                return {"daily_limit": settings.daily_token_limit, "used_today": 0, "remaining": settings.daily_token_limit}
            if quota.reset_at != date.today():
                return {"daily_limit": quota.daily_limit, "used_today": 0, "remaining": quota.daily_limit}
            return {
                "daily_limit": quota.daily_limit,
                "used_today": quota.used_today,
                "remaining": max(0, quota.daily_limit - quota.used_today),
            }

    async def log_call(
        self,
        user_id: str,
        task_type: str,
        model_name: str,
        tokens_input: int,
        tokens_output: int,
        from_cache: bool,
        success: bool,
        duration_ms: int,
        content_summary: str = "",
        error_message: str = "",
    ):
        """Log an API call (summary only, no original content)."""
        from app.models import APICallLog
        async with async_session() as session:
            log = APICallLog(
                user_id=user_id,
                task_type=task_type,
                model_name=model_name,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                cost_estimate=self._estimate_cost(model_name, tokens_input, tokens_output),
                from_cache=from_cache,
                success=success,
                error_message=error_message[:500] if error_message else "",
                content_summary=content_summary[:200] if content_summary else "",
                duration_ms=duration_ms,
            )
            session.add(log)
            await session.commit()

    def _estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Rough cost estimate in USD per 1K tokens"""
        rates = {
            "gpt-4o": (0.005, 0.015),
            "gpt-4o-mini": (0.00015, 0.0006),
            "deepseek-chat": (0.00014, 0.00028),
            "qwen-turbo": (0.0004, 0.0012),
            "ernie-bot": (0.001, 0.003),
            "ollama": (0, 0),  # local is free
        }
        in_rate, out_rate = rates.get(model, (0.001, 0.003))
        return (input_tokens / 1000) * in_rate + (output_tokens / 1000) * out_rate


rate_limiter = RateLimiter()
