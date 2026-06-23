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

import httpx

from config import settings

from . import _aggregator_client as agg
from .base import VideoProvider


class AggregatorVideoProvider(VideoProvider):
    def __init__(self) -> None:
        self.model = settings.video_model

    def generate_clip(self, prompt, anchor_image, duration_seconds, out_path) -> Path:
        image_url: Optional[str] = None
        if anchor_image is not None and Path(anchor_image).exists():
            image_url = _upload_to_fal(Path(anchor_image))

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


def _upload_to_fal(path: Path) -> str:
    """Upload a local file to fal storage and return its public URL.

    OPERATOR VERIFY: fal exposes a storage upload endpoint; the official
    ``fal-client`` SDK wraps it as ``fal_client.upload_file``.  This minimal
    HTTP version requests an upload target then PUTs the bytes.  If your
    aggregator differs (e.g. Replicate accepts data URLs directly), replace
    this helper accordingly.
    """
    if settings.aggregator == "replicate":
        # Replicate accepts data: URIs for image inputs.
        import base64
        import mimetypes

        mime = mimetypes.guess_type(str(path))[0] or "image/png"
        b64 = base64.b64encode(path.read_bytes()).decode()
        return f"data:{mime};base64,{b64}"

    headers = {"Authorization": f"Key {settings.aggregator_api_key}"}
    with httpx.Client(timeout=120) as client:
        init = client.post(
            "https://rest.alpha.fal.ai/storage/upload/initiate",
            headers=headers,
            json={"file_name": path.name, "content_type": "image/png"},
        )
        init.raise_for_status()
        info = init.json()
        upload_url = info["upload_url"]
        put = client.put(upload_url, content=path.read_bytes(), headers={"Content-Type": "image/png"})
        put.raise_for_status()
        return info["file_url"]
