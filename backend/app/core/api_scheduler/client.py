"""Unified API Client - the single entry point for all LLM calls"""
import asyncio
import time
import json
import re
import contextvars
from enum import Enum
from dataclasses import dataclass, field
from typing import Any
from app.config import settings
from .adapters.base import BaseModelAdapter, AdapterConfig, AdapterResponse
from .adapters.openai import OpenAICompatAdapter, DeepSeekAdapter, OllamaAdapter
from .adapters.anthropic import AnthropicAdapter
from .cache import cache_manager, compute_cache_key, compute_config_hash
from .rate_limiter import rate_limiter

# Context variable to carry the current user's ID through the request lifecycle.
# Set by load_user_keys_for_request() in route handlers.
_current_user_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "api_current_user_id", default="local_user"
)


def set_current_user_id(user_id: str) -> None:
    """Set the current user ID for this request context."""
    _current_user_id.set(user_id)


def get_current_user_id() -> str:
    """Get the current user ID from the request context."""
    return _current_user_id.get()


class TaskType(str, Enum):
    KNOWLEDGE_TREE = "knowledge_tree"
    QUIZ_GEN = "quiz_gen"
    FLASHCARD_GEN = "flashcard_gen"
    GAME_GEN = "game_gen"
    OUTLINE_GEN = "outline_gen"
    CHAT = "chat"
    VARIANT_QUESTION = "variant_question"


@dataclass
class GenerationConfig:
    model: str = "claude-opus-4-6"
    fallback_models: list[str] = field(default_factory=list)
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 1.0
    cache_ttl_days: int = 30
    max_retries: int = 2
    timeout: int = 120


@dataclass
class RequestContext:
    user_id: str = "local_user"
    project_id: str = "default"
    api_key_level: str = "personal"  # teacher/student/personal


@dataclass
class GenerationResult:
    content: str
    raw_content: str
    model_used: str
    tokens_input: int
    tokens_output: int
    from_cache: bool
    cost_estimate: float
    duration_ms: int


class UnifiedAPIClient:
    """Unified entry point for all AI generation requests.

    Handles: caching, rate limiting, model routing, retry, response normalization.
    """

    def __init__(self):
        self._adapters: dict[str, BaseModelAdapter] = {}
        self._adapter_configs: dict[str, dict] = {}

    def configure_adapter(
        self,
        provider: str,
        api_key: str,
        base_url: str | None = None,
        model_name: str | None = None,
    ):
        """Register an API adapter with credentials."""
        if provider in ("openai", "gpt-4o", "gpt-4o-mini"):
            adapter = OpenAICompatAdapter(
                api_key=api_key,
                base_url=base_url or "https://api.openai.com/v1",
                model_name=model_name or "gpt-4o",
            )
        elif provider == "anthropic":
            adapter = AnthropicAdapter(
                api_key=api_key,
                base_url=base_url or "https://api.anthropic.com/v1",
                model_name=model_name or "claude-sonnet-4-6",
            )
        elif provider == "deepseek":
            adapter = DeepSeekAdapter(api_key=api_key)
        elif provider == "ollama":
            adapter = OllamaAdapter(
                model_name=model_name or "qwen2.5:7b",
                base_url=base_url or "http://localhost:11434/v1",
            )
        else:
            # Generic OpenAI-compatible
            adapter = OpenAICompatAdapter(
                api_key=api_key,
                base_url=base_url or "https://api.openai.com/v1",
                model_name=model_name or provider,
            )
        adapter.provider = provider
        self._adapters[provider] = adapter
        self._adapter_configs[provider] = {
            "api_key": api_key,
            "base_url": base_url,
            "model_name": model_name,
        }

    def get_adapter(self, model_ref: str, user_id: str | None = None) -> BaseModelAdapter:
        """Get adapter by model reference. Supports 'provider/model_name' format.
        Falls back to any configured adapter if the exact provider isn't found.

        When user_id is provided and not "local_user", tries a user-scoped
        adapter first (keyed as 'provider_userid'), then falls back to global.
        """
        # Fall back to contextvar if no explicit user_id
        if not user_id or user_id == "local_user":
            ctxv = _current_user_id.get()
            if ctxv != "local_user":
                user_id = ctxv

        if "/" in model_ref:
            provider, model_name = model_ref.split("/", 1)
        else:
            provider = model_ref

        # Try user-scoped adapter first
        if user_id and user_id != "local_user":
            user_provider = f"{provider}_{user_id}"
            if user_provider in self._adapters:
                return self._adapters[user_provider]

        if provider not in self._adapters:
            # Try environment-configured key
            import os
            env_key_map = {
                "deepseek": "DEEPSEEK_API_KEY",
                "openai": "OPENAI_API_KEY",
                "gpt-4o": "OPENAI_API_KEY",
                "gpt-4o-mini": "OPENAI_API_KEY",
            }
            env_var = env_key_map.get(provider)
            if env_var and os.getenv(env_var):
                self.configure_adapter(provider, os.getenv(env_var))
            elif self._adapters:
                # Fall back to first configured adapter (common case: single API key)
                fallback = list(self._adapters.keys())[0]
                logger = __import__("logging").getLogger("knowall")
                logger.info("Using fallback adapter '%s' for model '%s'", fallback, model_ref)
                return self._adapters[fallback]
            else:
                raise ValueError(
                    f"No adapter configured for '{provider}'. "
                    f"Call configure_adapter() first or set environment variable."
                )

        return self._adapters[provider]

    async def generate(
        self,
        task_type: TaskType,
        messages: list[dict[str, str]],
        prompt_template_id: str,
        generation_content: str,
        config: GenerationConfig | None = None,
        context: RequestContext | None = None,
    ) -> GenerationResult:
        """Main generation entry point.

        Args:
            task_type: Type of generation task
            messages: Full chat messages (system + user)
            prompt_template_id: Identifier for the prompt template
            generation_content: The actual content text (for cache key computation)
            config: Generation configuration
            context: User/request context
        """
        config = config or GenerationConfig()
        context = context or RequestContext()

        # If no explicit user_id, fall back to contextvar (set by route handler)
        if context.user_id == "local_user":
            ctxv_user_id = _current_user_id.get()
            if ctxv_user_id != "local_user":
                context.user_id = ctxv_user_id

        cache_hit = False

        # 1. Compute cache key
        config_hash = compute_config_hash(config.temperature, config.top_p, config.max_tokens)
        cache_key = compute_cache_key(
            generation_content, prompt_template_id, config.model, config_hash
        )

        # 2. Check cache
        cached = await cache_manager.get(cache_key)
        if cached:
            return GenerationResult(
                content=cached,
                raw_content="",
                model_used=config.model + "(cache)",
                tokens_input=0,
                tokens_output=0,
                from_cache=True,
                cost_estimate=0,
                duration_ms=0,
            )

        # 3. Check quota
        allowed, msg = await rate_limiter.check_quota(context.user_id, len(generation_content) // 4)
        if not allowed:
            raise QuotaExceededError(msg)

        # 4. Acquire concurrency slot
        await rate_limiter.acquire(context.user_id)

        try:
            # 5. Try primary model, fall back on failure
            models_to_try = [config.model] + config.fallback_models
            last_error = None
            start_time = time.time()

            for attempt, model_ref in enumerate(models_to_try):
                try:
                    adapter = self.get_adapter(model_ref, user_id=context.user_id)
                    response = await adapter.chat_completion(
                        messages,
                        AdapterConfig(
                            temperature=config.temperature,
                            max_tokens=config.max_tokens,
                            top_p=config.top_p,
                            timeout=config.timeout,
                        ),
                    )

                    # 6. Normalize response
                    normalized = self._normalize_response(response.content, task_type)
                    duration_ms = int((time.time() - start_time) * 1000)

                    # 7. Record usage
                    await rate_limiter.record_usage(
                        context.user_id, response.tokens_input, response.tokens_output
                    )

                    # 8. Cache successful result
                    await cache_manager.set(
                        cache_key=cache_key,
                        response_content=normalized,
                        model_used=model_ref,
                        tokens_input=response.tokens_input,
                        tokens_output=response.tokens_output,
                        ttl_days=config.cache_ttl_days,
                    )

                    # 9. Log call
                    await rate_limiter.log_call(
                        user_id=context.user_id,
                        task_type=task_type.value,
                        model_name=model_ref,
                        tokens_input=response.tokens_input,
                        tokens_output=response.tokens_output,
                        from_cache=False,
                        success=True,
                        duration_ms=duration_ms,
                        content_summary=normalized[:200],
                    )

                    return GenerationResult(
                        content=normalized,
                        raw_content=response.raw_content,
                        model_used=model_ref,
                        tokens_input=response.tokens_input,
                        tokens_output=response.tokens_output,
                        from_cache=False,
                        cost_estimate=rate_limiter._estimate_cost(
                            model_ref, response.tokens_input, response.tokens_output
                        ),
                        duration_ms=duration_ms,
                    )

                except Exception as e:
                    last_error = e
                    if attempt < config.max_retries:
                        wait_time = 2 ** attempt  # exponential backoff
                        await asyncio.sleep(wait_time)
                    continue

            # All models failed
            duration_ms = int((time.time() - start_time) * 1000)
            await rate_limiter.log_call(
                user_id=context.user_id,
                task_type=task_type.value,
                model_name=config.model,
                tokens_input=0,
                tokens_output=0,
                from_cache=False,
                success=False,
                duration_ms=duration_ms,
                error_message=str(last_error),
            )
            raise AllModelsFailedError(f"All models failed: {last_error}")

        finally:
            rate_limiter.release()

    async def analyze_image(
        self,
        image_base64: str,
        image_type: str,
        prompt: str,
        context_text: str = "",
        model: str = "gpt-4o",
        user_id: str | None = None,
    ) -> str:
        """Analyze a single image using a vision-capable model.

        Returns the text description generated by the model.
        """
        # Fall back to contextvar if no explicit user_id
        if not user_id or user_id == "local_user":
            ctxv = _current_user_id.get()
            if ctxv != "local_user":
                user_id = ctxv

        adapter = self.get_adapter(model, user_id=user_id)

        # Build multimodal message
        content_blocks = []
        if context_text:
            content_blocks.append({
                "type": "text",
                "text": f"该图片在文档中的上下文信息：\n{context_text}",
            })
        content_blocks.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{image_type};base64,{image_base64}",
                "detail": "low",
            },
        })
        content_blocks.append({"type": "text", "text": prompt})

        messages = [{"role": "user", "content": content_blocks}]

        response = await adapter.chat_completion(
            messages=messages,
            config=AdapterConfig(temperature=0.3, max_tokens=512),
        )
        return response.content

    def _normalize_response(self, content: str, task_type: TaskType) -> str:
        """Normalize model output: strip markdown code fences, validate JSON."""
        if task_type in (
            TaskType.KNOWLEDGE_TREE,
            TaskType.QUIZ_GEN,
            TaskType.FLASHCARD_GEN,
            TaskType.GAME_GEN,
        ):
            # Extract JSON from markdown code blocks
            content = self._extract_json(content)
        return content.strip()

    @staticmethod
    def _extract_json(text: str) -> str:
        """Extract JSON from text, stripping markdown fences."""
        # Try to find JSON block in markdown
        pattern = r"```(?:json)?\s*([\s\S]*?)```"
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
        # Try to find JSON object directly
        brace_start = text.find("{")
        bracket_start = text.find("[")
        if brace_start == -1 and bracket_start == -1:
            return text
        start = brace_start if brace_start != -1 and (bracket_start == -1 or brace_start < bracket_start) else bracket_start
        return text[start:].strip()


class QuotaExceededError(Exception):
    pass


class AllModelsFailedError(Exception):
    pass


# Singleton instance
api_client = UnifiedAPIClient()
