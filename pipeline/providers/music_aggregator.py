"""Single background-music track via the aggregator (default: fal Stable Audio).

OPERATOR VERIFY: Confirm ``MUSIC_MODEL`` and its input schema.  Music models
commonly accept ``prompt`` plus a duration field (``seconds_total`` for Stable
Audio).  Adjust ``payload`` to match your chosen model.
"""
from __future__ import annotations

from pathlib import Path

from config import settings

from . import _aggregator_client as agg
from .base import MusicProvider


class AggregatorMusicProvider(MusicProvider):
    def __init__(self, cfg=None) -> None:
        self.cfg = cfg or settings
        self.model = self.cfg.music_model

    def generate_music(self, prompt: str, duration_seconds: int, out_path: Path) -> Path:
        payload = {
            "prompt": prompt,
            "seconds_total": int(duration_seconds),
        }
        result = agg.submit_and_wait(self.model, payload)
        url = agg.extract_url(result, "audio")
        if not url:
            raise RuntimeError(f"no audio URL in aggregator result: {result}")
        return agg.download(url, out_path)
