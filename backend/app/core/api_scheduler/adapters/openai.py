"""OpenAI-compatible adapter (works for OpenAI, DeepSeek, Ollama, vLLM, etc.)"""
import json
import asyncio
from typing import AsyncIterator
import httpx
from .base import BaseModelAdapter, AdapterConfig, AdapterResponse
from .http_utils import sync_post

# tiktoken 词表在首次调用时会联网下载，可能卡死启动。改为懒加载 + 纯字符兜底。
_encoder = None


def _get_encoder():
    """懒加载 tiktoken encoder，失败则用纯字符估算（绝不阻塞启动）。"""
    global _encoder
    if _encoder is not None:
        return _encoder
    try:
        import tiktoken
        _encoder = tiktoken.encoding_for_model("gpt-4o")
    except Exception:
        # 无词表时的兜底：用字符数×0.5 粗略估算 token（仅影响统计，不影响功能）
        class _FallbackEncoder:
            def encode(self, text: str):
                return text  # 不作为真正 token 使用
            @staticmethod
            def _estimate(text: str) -> int:
                return max(1, len(text) * 2 // 3)
        _encoder = _FallbackEncoder()
    return _encoder


class OpenAICompatAdapter(BaseModelAdapter):
    """Adapter for any OpenAI-compatible API (OpenAI, DeepSeek, Ollama, vLLM, etc.)"""

    provider = "openai_compat"

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1", model_name: str = "gpt-4o"):
        super().__init__(api_key, base_url)
        self.model_name = model_name
        self._encoder = None

    async def chat_completion(
        self, messages: list[dict[str, str]], config: AdapterConfig
    ) -> AdapterResponse:
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = self._build_headers()
        headers["User-Agent"] = "KnowAll-Studio/1.0"
        headers["Accept"] = "application/json"
        payload = {
            "model": self.model_name,
            "messages": self._normalize_messages(messages),
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "top_p": config.top_p,
        }
        payload.update(config.extra)

        data = await asyncio.to_thread(sync_post, url, headers, payload, config.timeout)
        return self._parse_response(data)

    def count_tokens(self, text: str) -> int:
        enc = _get_encoder()
        if hasattr(enc, "_estimate"):
            return enc._estimate(text)
        return len(enc.encode(text))

    async def stream_chat_completion(
        self, messages: list[dict[str, str]], config: AdapterConfig
    ) -> AsyncIterator[str]:
        """Stream chat completions as an async iterator of text deltas (SSE)."""
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = self._build_headers()
        headers["Accept"] = "text/event-stream"
        headers["User-Agent"] = "YuanQi-Dazi/1.0"
        payload = {
            "model": self.model_name,
            "messages": self._normalize_messages(messages),
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "top_p": config.top_p,
            "stream": True,
        }
        payload.update(config.extra)

        async with httpx.AsyncClient(timeout=config.timeout, headers=headers) as client:
            async with client.stream("POST", url, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    piece = delta.get("content")
                    if piece:
                        yield piece

    def _parse_response(self, data: dict) -> AdapterResponse:
        choice = data["choices"][0]
        usage = data.get("usage", {})
        return AdapterResponse(
            content=choice["message"]["content"],
            raw_content=json.dumps(data, ensure_ascii=False),
            model=data.get("model", self.model_name),
            tokens_input=usage.get("prompt_tokens", 0),
            tokens_output=usage.get("completion_tokens", 0),
            finish_reason=choice.get("finish_reason", "stop"),
        )


class DeepSeekAdapter(OpenAICompatAdapter):
    provider = "deepseek"
    model_name = "deepseek-chat"

    def __init__(self, api_key: str):
        super().__init__(api_key, base_url="https://api.deepseek.com/v1", model_name="deepseek-chat")


class OllamaAdapter(OpenAICompatAdapter):
    provider = "ollama"

    def __init__(self, model_name: str = "qwen2.5:7b", base_url: str = "http://localhost:11434/v1"):
        super().__init__(api_key="ollama", base_url=base_url, model_name=model_name)

    def _build_headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json"}  # Ollama needs no auth header
