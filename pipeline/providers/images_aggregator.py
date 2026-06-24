"""Anchor-image generation via the aggregator (default: fal.ai Flux).

OPERATOR VERIFY: Confirm ``IMAGE_MODEL`` and its input schema.  The default
``fal-ai/flux/dev`` accepts ``prompt`` and ``image_size``; other Flux variants
may name fields differently.  See _aggregator_client.py for the shared notes.
"""
from __future__ import annotations

from pathlib import Path

from config import settings

from . import _aggregator_client as agg
from .base import ImageProvider


class AggregatorImageProvider(ImageProvider):
    def __init__(self, cfg=None) -> None:
        self.cfg = cfg or settings
        self.model = self.cfg.image_model

    def generate_image(self, prompt: str, out_path: Path) -> Path:
        payload = {
            "prompt": prompt,
            "image_size": "landscape_16_9",
            "num_images": 1,
        }
        result = agg.submit_and_wait(self.model, payload)
        url = agg.extract_url(result, "image")
        if not url:
            raise RuntimeError(f"no image URL in aggregator result: {result}")
        return agg.download(url, out_path)
