"""Base adapter for all LLM providers"""
from abc import ABC, abstractmethod
from typing import Any
from dataclasses import dataclass, field


@dataclass
class AdapterConfig:
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 1.0
    timeout: int = 120
    extra: dict = field(default_factory=dict)


@dataclass
class AdapterResponse:
    content: str
    raw_content: str
    model: str
    tokens_input: int = 0
    tokens_output: int = 0
    finish_reason: str = "stop"


class BaseModelAdapter(ABC):
    """Abstract base for all model adapters"""

    provider: str = "base"
    base_url: str = ""

    def __init__(self, api_key: str, base_url: str | None = None):
        self.api_key = api_key
        if base_url:
            self.base_url = base_url

    @abstractmethod
    async def chat_completion(
        self, messages: list[dict[str, str]], config: AdapterConfig
    ) -> AdapterResponse:
        """Call model API and return standardized response"""
        ...

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Estimate token count for text"""
        ...

    def validate_response(self, raw: Any) -> AdapterResponse:
        """Validate and normalize API response. Override in subclasses for provider-specific logic."""
        return raw if isinstance(raw, AdapterResponse) else AdapterResponse(
            content=str(raw),
            raw_content=str(raw),
            model="unknown",
        )

    def _build_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _normalize_messages(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        """Normalize messages to OpenAI chat format"""
        return messages
