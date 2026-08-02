"""Shared HTTP utility for LLM adapter sync POST calls."""
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


def sync_post(url: str, headers: dict, payload: dict, timeout: int) -> dict:
    """Synchronous HTTP POST using urllib (most reliable cross-platform)."""
    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {body[:500]}")
    except URLError as e:
        raise RuntimeError(f"Connection failed: {e.reason}")
