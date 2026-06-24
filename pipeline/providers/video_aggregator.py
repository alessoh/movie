"""Per-shot clip generation via the aggregator (default: fal.ai Kling i2v).

OPERATOR VERIFY: Confirm ``VIDEO_MODEL`` and its input schema.  Image-to-video
models commonly take ``prompt``, an ``image_url`` (the anchor), and a
``duration`` field whose units/allowed values vary (Kling uses "5"/"10" second
strings; Veo differs).  Adjust ``_build_payload`` to match your chosen model.
The anchor image is uploaded to fal's storage when present so the model can
reference it by URL.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from config import settings

from . import _aggregator_client as agg
from .base import VideoProvider


class AggregatorVideoProvider(VideoProvider):
    def __init__(self, cfg=None) -> None:
        self.cfg = cfg or settings
        self.model = self.cfg.video_model

    def generate_clip(self, prompt, anchor_image, duration_seconds, out_path) -> Path:
        image_url: Optional[str] = None
        if anchor_image is not None and Path(anchor_image).exists():
            image_url = _image_reference(Path(anchor_image))

        payload = {"prompt": prompt}
        if image_url:
            payload["image_url"] = image_url
        # Kling accepts "5" or "10"; pick the nearest. Operator: adjust per model.
        payload["duration"] = "10" if duration_seconds > 7 else "5"

        result = agg.submit_and_wait(self.model, payload)
        url = agg.extract_url(result, "video")
        if not url:
            raise RuntimeError(f"no video URL in aggregator result: {result}")
        return agg.download(url, out_path)


def _image_reference(path: Path) -> str:
    """Return a value usable for an ``image_url`` input field.

    Both fal.ai and Replicate accept a base64 ``data:`` URI for image inputs
    (this is what ``fal_client.encode_file`` produces), so we inline the anchor
    directly. This avoids any dependency on a separate file-upload endpoint.

    OPERATOR VERIFY: a few models require a hosted https URL rather than a data
    URI. If yours does, upload the file to your own storage (or fal storage via
    the official ``fal-client`` SDK) and return that URL here instead.
    """
    import base64
    import mimetypes

    mime = mimetypes.guess_type(str(path))[0] or "image/png"
    b64 = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime};base64,{b64}"
