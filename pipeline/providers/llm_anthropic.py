"""Anthropic Claude adapter for the language-model passes.

OPERATOR VERIFY: This targets the Anthropic Messages API
(https://docs.anthropic.com/en/api/messages).  Confirm the current endpoint,
the ``anthropic-version`` header value, and your model id (``LLM_MODEL``)
against the live docs.  The request/response shapes used here are the stable
documented ones at time of writing.
"""
from __future__ import annotations

import httpx

from config import settings

from .base import LLMProvider

_API_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"


class AnthropicLLMProvider(LLMProvider):
    def __init__(self, cfg=None) -> None:
        self.cfg = cfg or settings
        if not self.cfg.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        self.model = self.cfg.llm_model

    def complete(self, system: str, prompt: str, max_tokens: int = 4000) -> str:
        headers = {
            "x-api-key": self.cfg.anthropic_api_key,
            "anthropic-version": _API_VERSION,
            "content-type": "application/json",
        }
        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }
        with httpx.Client(timeout=120) as client:
            resp = client.post(_API_URL, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
        # Response: {"content": [{"type": "text", "text": "..."}], ...}
        parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
        text = "".join(parts).strip()
        if not text:
            raise RuntimeError("Anthropic returned an empty completion")
        return text
