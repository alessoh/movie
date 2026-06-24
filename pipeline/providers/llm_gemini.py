"""Google Gemini adapter for the language-model passes.

Selected with ``LLM_PROVIDER=gemini``.  Set ``LLM_MODEL`` to a Gemini model id
(e.g. ``gemini-2.0-flash`` or ``gemini-1.5-pro``) and provide ``GEMINI_API_KEY``.

OPERATOR VERIFY: This targets the Google Generative Language API
(https://ai.google.dev/api/generate-content).  Confirm the current endpoint,
the model id (``LLM_MODEL``), and that ``system_instruction`` is supported by
your chosen model.  The request/response shapes used here are the documented
ones for ``v1beta`` at time of writing.
"""
from __future__ import annotations

import httpx

from config import settings

from .base import LLMProvider

_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiLLMProvider(LLMProvider):
    def __init__(self) -> None:
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        self.model = settings.llm_model

    def complete(self, system: str, prompt: str, max_tokens: int = 4000) -> str:
        url = f"{_BASE}/{self.model}:generateContent"
        headers = {
            "content-type": "application/json",
            "x-goog-api-key": settings.gemini_api_key,
        }
        body = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": 0.7,
                # Ask for raw JSON; our parser also tolerates fenced output.
                "responseMimeType": "application/json",
            },
        }
        with httpx.Client(timeout=120) as client:
            resp = client.post(url, headers=headers, json=body)
            if resp.status_code >= 400:
                # Surface Google's actual explanation (e.g. "API key not valid",
                # "model not found") instead of a bare status code.
                detail = ""
                try:
                    detail = resp.json().get("error", {}).get("message", "")
                except Exception:
                    detail = resp.text[:300]
                raise RuntimeError(f"Gemini HTTP {resp.status_code}: {detail}")
            data = resp.json()

        # Response: {"candidates": [{"content": {"parts": [{"text": "..."}]}}]}
        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts).strip()
        except (KeyError, IndexError, TypeError):
            text = ""
        if not text:
            raise RuntimeError(f"Gemini returned no usable text: {data}")
        return text
