"""OpenAI adapter for the language-model passes.

Selected with ``LLM_PROVIDER=openai``.  Set ``LLM_MODEL`` to an OpenAI model id
(e.g. ``gpt-4o`` or ``gpt-4o-mini``) and provide ``OPENAI_API_KEY``.  Any
OpenAI-compatible endpoint also works via ``OPENAI_BASE_URL``.

OPERATOR VERIFY: This targets the Chat Completions API
(https://platform.openai.com/docs/api-reference/chat).  Confirm the endpoint,
the model id (``LLM_MODEL``), and -- if you point ``OPENAI_BASE_URL`` at a
compatible gateway (Azure, OpenRouter, a local server) -- that the request and
response shapes match.
"""
from __future__ import annotations

import os

import httpx

from config import settings

from .base import LLMProvider


class OpenAILLMProvider(LLMProvider):
    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        self.model = settings.llm_model
        self.base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")

    def complete(self, system: str, prompt: str, max_tokens: int = 4000) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {settings.openai_api_key}",
        }
        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        with httpx.Client(timeout=120) as client:
            resp = client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
        try:
            text = (data["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, TypeError):
            text = ""
        if not text:
            raise RuntimeError(f"OpenAI returned no usable text: {data}")
        return text
