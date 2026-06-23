"""Shared HTTP client for the model-hosting aggregator (fal.ai / Replicate).

Three integrations -- image, video, music -- collapse into one consistent
HTTP pattern and one key by going through this client.

OPERATOR VERIFY: The default implementation targets the **fal.ai queue API**
(https://docs.fal.ai/model-endpoints/queue).  Confirm:
  * Base URLs: submit at ``https://queue.fal.run/{model_id}``; poll/status and
    result are returned as absolute ``status_url`` / ``response_url`` fields.
  * Auth header format: ``Authorization: Key <AGGREGATOR_API_KEY>``.
  * The result JSON field names for each model (``images[].url``, ``video.url``,
    ``audio_file.url`` / ``audio.url``).  These vary per model; adjust the
    extraction helpers below if your chosen models differ.

A minimal Replicate code path is included and selected by ``AGGREGATOR=replicate``.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from config import settings

_POLL_INTERVAL = 3.0
_POLL_TIMEOUT = 600.0  # 10 minutes hard ceiling per generation


def _auth_headers() -> Dict[str, str]:
    if settings.aggregator == "replicate":
        return {"Authorization": f"Bearer {settings.aggregator_api_key}"}
    # fal.ai
    return {"Authorization": f"Key {settings.aggregator_api_key}"}


def submit_and_wait(model_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Submit a job to the aggregator and poll until it completes.

    Returns the final result JSON.  Raises on timeout or error.
    """
    if not settings.aggregator_api_key:
        raise RuntimeError("AGGREGATOR_API_KEY is not set")
    if settings.aggregator == "replicate":
        return _replicate_submit_and_wait(model_id, payload)
    return _fal_submit_and_wait(model_id, payload)


# --------------------------------------------------------------------------- #
# fal.ai queue API
# --------------------------------------------------------------------------- #
def _fal_submit_and_wait(model_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    submit_url = f"https://queue.fal.run/{model_id}"
    headers = _auth_headers()
    with httpx.Client(timeout=60) as client:
        resp = client.post(submit_url, headers=headers, json=payload)
        resp.raise_for_status()
        job = resp.json()

        status_url = job.get("status_url")
        response_url = job.get("response_url")
        if not status_url:
            # Some models return the result synchronously.
            return job

        deadline = time.monotonic() + _POLL_TIMEOUT
        while time.monotonic() < deadline:
            st = client.get(status_url, headers=headers)
            st.raise_for_status()
            status = st.json().get("status")
            if status == "COMPLETED":
                final = client.get(response_url, headers=headers)
                final.raise_for_status()
                return final.json()
            if status in ("FAILED", "ERROR", "CANCELLED"):
                raise RuntimeError(f"aggregator job failed: {st.json()}")
            time.sleep(_POLL_INTERVAL)
    raise TimeoutError(f"aggregator job timed out for {model_id}")


# --------------------------------------------------------------------------- #
# Replicate predictions API
# --------------------------------------------------------------------------- #
def _replicate_submit_and_wait(model_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    # model_id for replicate is expected to be a full version hash or
    # "owner/name". This uses the predictions endpoint with model routing.
    headers = _auth_headers()
    url = f"https://api.replicate.com/v1/models/{model_id}/predictions"
    with httpx.Client(timeout=60) as client:
        resp = client.post(url, headers=headers, json={"input": payload})
        resp.raise_for_status()
        pred = resp.json()
        get_url = pred.get("urls", {}).get("get")
        deadline = time.monotonic() + _POLL_TIMEOUT
        while get_url and time.monotonic() < deadline:
            r = client.get(get_url, headers=headers)
            r.raise_for_status()
            pred = r.json()
            status = pred.get("status")
            if status == "succeeded":
                return pred
            if status in ("failed", "canceled"):
                raise RuntimeError(f"replicate prediction failed: {pred.get('error')}")
            time.sleep(_POLL_INTERVAL)
    raise TimeoutError(f"replicate prediction timed out for {model_id}")


# --------------------------------------------------------------------------- #
# Result extraction + download helpers
# --------------------------------------------------------------------------- #
def extract_url(result: Dict[str, Any], kind: str) -> Optional[str]:
    """Best-effort extraction of an asset URL from a result payload.

    ``kind`` is one of "image", "video", "audio".  Different models nest the
    URL differently; the common shapes are handled here.
    """
    if settings.aggregator == "replicate":
        out = result.get("output")
        if isinstance(out, str):
            return out
        if isinstance(out, list) and out:
            return out[0]
        if isinstance(out, dict):
            return out.get("url") or out.get(kind)
        return None

    # fal.ai shapes
    if kind == "image":
        imgs = result.get("images")
        if isinstance(imgs, list) and imgs:
            first = imgs[0]
            return first.get("url") if isinstance(first, dict) else first
        if isinstance(result.get("image"), dict):
            return result["image"].get("url")
    if kind == "video":
        vid = result.get("video")
        if isinstance(vid, dict):
            return vid.get("url")
        if isinstance(vid, str):
            return vid
    if kind == "audio":
        for key in ("audio_file", "audio"):
            node = result.get(key)
            if isinstance(node, dict):
                return node.get("url")
            if isinstance(node, str):
                return node
    # Last resort: a top-level "url".
    return result.get("url")


def download(url: str, out_path: Path) -> Path:
    with httpx.Client(timeout=300, follow_redirects=True) as client:
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            with open(out_path, "wb") as fh:
                for chunk in resp.iter_bytes():
                    fh.write(chunk)
    if out_path.stat().st_size == 0:
        raise RuntimeError(f"downloaded empty file from {url}")
    return out_path
