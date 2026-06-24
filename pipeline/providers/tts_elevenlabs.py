"""Narrator voice via ElevenLabs text-to-speech.

OPERATOR VERIFY: Targets the ElevenLabs TTS endpoint
(https://elevenlabs.io/docs/api-reference/text-to-speech).  Confirm:
  * ``TTS_VOICE_ID`` is a real voice id from your account (the default
    "narrator-default" is a placeholder and MUST be replaced).
  * The ``model_id`` below ("eleven_multilingual_v2") still exists.
The endpoint returns raw audio bytes (MP3 by default).
"""
from __future__ import annotations

from pathlib import Path

import httpx

from config import settings

from .base import TTSProvider

_BASE = "https://api.elevenlabs.io/v1/text-to-speech"


class ElevenLabsTTSProvider(TTSProvider):
    def __init__(self, cfg=None) -> None:
        self.cfg = cfg or settings
        if not self.cfg.elevenlabs_api_key:
            raise RuntimeError("ELEVENLABS_API_KEY is not set")
        self.voice_id = self.cfg.tts_voice_id

    def synthesize(self, text: str, out_path: Path) -> Path:
        url = f"{_BASE}/{self.voice_id}"
        headers = {
            "xi-api-key": self.cfg.elevenlabs_api_key,
            "content-type": "application/json",
            "accept": "audio/mpeg",
        }
        body = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }
        with httpx.Client(timeout=120) as client:
            resp = client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.content
        if not data:
            raise RuntimeError("ElevenLabs returned empty audio")
        out_path.write_bytes(data)
        return out_path
