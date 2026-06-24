"""Central configuration module.

Every tunable parameter and every secret key is loaded here from the
environment (optionally via a local ``.env`` file).  No other module reads
``os.environ`` for these values; they always go through ``settings`` so that
keys have exactly one ingress point and can never leak to the client.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional at runtime
    pass


BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage" / "sessions"
WEB_DIR = BASE_DIR / "web"


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _get_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass
class Settings:
    # Keys (server-side only)
    anthropic_api_key: str = field(default_factory=lambda: _get("ANTHROPIC_API_KEY"))
    gemini_api_key: str = field(default_factory=lambda: _get("GEMINI_API_KEY"))
    openai_api_key: str = field(default_factory=lambda: _get("OPENAI_API_KEY"))
    aggregator_api_key: str = field(default_factory=lambda: _get("AGGREGATOR_API_KEY"))
    elevenlabs_api_key: str = field(default_factory=lambda: _get("ELEVENLABS_API_KEY"))

    # Provider selection
    llm_provider: str = field(default_factory=lambda: _get("LLM_PROVIDER", "anthropic"))
    image_provider: str = field(default_factory=lambda: _get("IMAGE_PROVIDER", "aggregator"))
    video_provider: str = field(default_factory=lambda: _get("VIDEO_PROVIDER", "aggregator"))
    tts_provider: str = field(default_factory=lambda: _get("TTS_PROVIDER", "elevenlabs"))
    music_provider: str = field(default_factory=lambda: _get("MUSIC_PROVIDER", "aggregator"))
    aggregator: str = field(default_factory=lambda: _get("AGGREGATOR", "fal"))

    # Model identifiers
    llm_model: str = field(default_factory=lambda: _get("LLM_MODEL", "claude-sonnet-4-6"))
    image_model: str = field(default_factory=lambda: _get("IMAGE_MODEL", "fal-ai/flux/dev"))
    video_model: str = field(
        default_factory=lambda: _get(
            "VIDEO_MODEL", "fal-ai/kling-video/v1/standard/image-to-video"
        )
    )
    music_model: str = field(default_factory=lambda: _get("MUSIC_MODEL", "fal-ai/stable-audio"))
    # Many music models cap clip length (Stable Audio ~47s). We request at most
    # this many seconds and loop the track to fill the movie. 0 = no cap.
    music_max_seconds: int = field(default_factory=lambda: _get_int("MUSIC_MAX_SECONDS", 47))
    tts_voice_id: str = field(default_factory=lambda: _get("TTS_VOICE_ID", "narrator-default"))

    # Movie shape
    target_duration_seconds: int = field(
        default_factory=lambda: _get_int("TARGET_DURATION_SECONDS", 120)
    )
    shot_count: int = field(default_factory=lambda: _get_int("SHOT_COUNT", 15))
    shot_length_seconds: int = field(default_factory=lambda: _get_int("SHOT_LENGTH_SECONDS", 8))

    # Guardrails
    max_retries_per_shot: int = field(default_factory=lambda: _get_int("MAX_RETRIES_PER_SHOT", 2))
    max_movies_per_session: int = field(
        default_factory=lambda: _get_int("MAX_MOVIES_PER_SESSION", 1)
    )
    failed_shot_fallback: str = field(
        default_factory=lambda: _get("FAILED_SHOT_FALLBACK", "hold_still")
    )
    session_ttl_minutes: int = field(default_factory=lambda: _get_int("SESSION_TTL_MINUTES", 60))
    max_upload_mb: int = field(default_factory=lambda: _get_int("MAX_UPLOAD_MB", 25))

    # Runtime
    run_mode: str = field(default_factory=lambda: _get("RUN_MODE", "real"))
    port: int = field(default_factory=lambda: _get_int("PORT", 8000))
    host: str = field(default_factory=lambda: _get("HOST", "0.0.0.0"))

    @property
    def is_mock(self) -> bool:
        return self.run_mode.lower() == "mock"

    def required_keys_present(self) -> List[str]:
        """Return a list of human-readable names of missing required keys.

        Only the keys actually needed by the selected providers in REAL mode
        are checked.  In mock mode nothing is required.
        """
        if self.is_mock:
            return []
        missing: List[str] = []
        llm_key_by_provider = {
            "anthropic": ("ANTHROPIC_API_KEY", self.anthropic_api_key),
            "gemini": ("GEMINI_API_KEY", self.gemini_api_key),
            "openai": ("OPENAI_API_KEY", self.openai_api_key),
        }
        if self.llm_provider in llm_key_by_provider:
            key_name, key_value = llm_key_by_provider[self.llm_provider]
            if not key_value:
                missing.append(key_name)
        aggregator_used = any(
            p == "aggregator"
            for p in (self.image_provider, self.video_provider, self.music_provider)
        )
        if aggregator_used and not self.aggregator_api_key:
            missing.append("AGGREGATOR_API_KEY")
        if self.tts_provider == "elevenlabs" and not self.elevenlabs_api_key:
            missing.append("ELEVENLABS_API_KEY")
        return missing


settings = Settings()

# Ensure storage exists on import so every module can rely on it.
STORAGE_DIR.mkdir(parents=True, exist_ok=True)
