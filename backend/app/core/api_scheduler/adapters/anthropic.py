"""Anthropic Messages API adapter"""
import json
import asyncio
import tiktoken
from .base import BaseModelAdapter, AdapterConfig, AdapterResponse
from .http_utils import sync_post


class AnthropicAdapter(BaseModelAdapter):
    """Adapter for Anthropic Messages API (and compatible endpoints like DeepSeek)."""

    provider = "anthropic"

    def __init__(self, api_key: str, base_url: str = "https://api.anthropic.com/v1", model_name: str = "claude-sonnet-4-6"):
        super().__init__(api_key, base_url)
        self.model_name = model_name
        self._api_version = "2023-06-01"
        try:
            self._encoder = tiktoken.encoding_for_model("gpt-4o")
        except Exception:
            self._encoder = tiktoken.get_encoding("cl100k_base")

    async def chat_completion(
        self, messages: list[dict[str, str]], config: AdapterConfig
    ) -> AdapterResponse:
        url = f"{self.base_url.rstrip('/')}/messages"
        headers = self._build_headers()
        headers.update({
            "anthropic-version": self._api_version,
            "Content-Type": "application/json",
        })

        # Convert OpenAI-format messages to Anthropic format
        system_prompt = ""
        anthropic_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                content = msg["content"]
                # Handle multimodal content (list of content blocks)
                if isinstance(content, list):
                    anthropic_content = self._convert_multimodal_content(content)
                else:
                    anthropic_content = content
                anthropic_messages.append({
                    "role": msg["role"],
                    "content": anthropic_content,
                })

        payload = {
            "model": self.model_name,
            "messages": anthropic_messages,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "top_p": config.top_p,
        }
        if system_prompt:
            payload["system"] = system_prompt
        payload.update(config.extra)

        data = await asyncio.to_thread(sync_post, url, headers, payload, config.timeout)
        return self._parse_response(data)

    def _convert_multimodal_content(self, content_blocks: list[dict]) -> list[dict]:
        """Convert OpenAI-format multimodal content blocks to Anthropic format."""
        anthropic_blocks = []
        for block in content_blocks:
            if block.get("type") == "text":
                anthropic_blocks.append({"type": "text", "text": block["text"]})
            elif block.get("type") == "image_url":
                image_url = block.get("image_url", {})
                url = image_url.get("url", "")
                # Parse data URL: data:image/png;base64,<data>
                if url.startswith("data:"):
                    import re
                    import base64
                    match = re.match(r"data:(image/\w+);base64,(.+)", url)
                    if match:
                        media_type = match.group(1)
                        img_data = match.group(2)
                        # Validate base64
                        try:
                            base64.b64decode(img_data)
                        except Exception:
                            continue
                        anthropic_blocks.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": img_data,
                            },
                        })
            # Skip unknown block types
        return anthropic_blocks

    def count_tokens(self, text: str) -> int:
        return len(self._encoder.encode(text))

    def _parse_response(self, data: dict) -> AdapterResponse:
        content_blocks = data.get("content", [])
        text = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")
        usage = data.get("usage", {})
        return AdapterResponse(
            content=text,
            raw_content=json.dumps(data, ensure_ascii=False),
            model=data.get("model", self.model_name),
            tokens_input=usage.get("input_tokens", 0),
            tokens_output=usage.get("output_tokens", 0),
            finish_reason=data.get("stop_reason", "stop"),
        )
