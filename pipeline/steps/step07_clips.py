"""Step 7 - Clip generation, the real-video core.

For each shot, call the video adapter with the shot's visual prompt plus its
anchor image, retry a failed/empty generation up to the configured maximum,
then apply the section-9 fallback (hold_still or drop_shot).

Returns a list of per-shot dicts:
    {"index": int, "shot": dict, "clip": Path|None, "degraded": bool, "dropped": bool}
The orchestrator owns timeline alignment from this output.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from config import settings
from pipeline import ffmpeg_utils as ff
from pipeline.providers.base import VideoProvider
from pipeline.steps.step06_anchors import anchor_for_shot

ProgressFn = Callable[[int, int, str], None]  # (current, total, message)


def generate_clips(
    video: VideoProvider,
    shot_list: dict,
    anchors: Dict[str, object],
    work_dir: Path,
    progress: Optional[ProgressFn] = None,
) -> List[dict]:
    clips_dir = work_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    shots = shot_list["shots"]
    total = len(shots)
    results: List[dict] = []

    for n, shot in enumerate(shots, start=1):
        if progress:
            progress(n, total, f"Filming shot {n} of {total}")
        out_path = clips_dir / f"shot_{shot['index']:02d}.mp4"
        anchor = anchor_for_shot(shot, anchors)
        clip, last_error = _generate_with_retry(video, shot, anchor, out_path)

        if clip is not None:
            results.append(
                {"index": shot["index"], "shot": shot, "clip": clip, "degraded": False, "dropped": False}
            )
            continue

        # All retries exhausted -> surface the real reason, then apply fallback.
        if progress and last_error:
            progress(n, total, f"Shot {n} clip failed: {last_error}")
        fallback = settings.failed_shot_fallback.lower()
        if fallback == "drop_shot":
            if progress:
                progress(n, total, f"Shot {n} failed; dropping it from the film.")
            results.append(
                {"index": shot["index"], "shot": shot, "clip": None, "degraded": False, "dropped": True}
            )
        else:  # hold_still (default)
            held = _hold_still(shot, anchor, out_path)
            if progress:
                progress(n, total, f"Shot {n} failed; holding a still frame instead.")
            results.append(
                {"index": shot["index"], "shot": shot, "clip": held, "degraded": True, "dropped": held is None}
            )
    return results


def _generate_with_retry(
    video: VideoProvider, shot: dict, anchor: Optional[Path], out_path: Path
) -> tuple[Optional[Path], Optional[str]]:
    """Return (clip_path, last_error). ``last_error`` is a short reason string
    when all attempts fail, so the orchestrator can log why."""
    attempts = settings.max_retries_per_shot + 1
    duration = int(shot["duration_seconds"])
    last_error: Optional[str] = None
    for attempt in range(attempts):
        try:
            video.generate_clip(shot["visual_prompt"], anchor, duration, out_path)
            if out_path.exists() and out_path.stat().st_size > 0 and ff.probe_duration(out_path) > 0.1:
                return out_path, None
            last_error = "provider returned an empty or unreadable clip"
        except Exception as exc:  # noqa: BLE001 - captured and surfaced, not hidden
            last_error = _short_error(exc)
        if attempt < attempts - 1:
            time.sleep(2 * (attempt + 1))  # short linear backoff
    return None, last_error


def _short_error(exc: Exception) -> str:
    """Compact, human-readable one-liner from an exception (incl. HTTP bodies)."""
    import httpx

    if isinstance(exc, httpx.HTTPStatusError):
        body = ""
        try:
            body = exc.response.text[:300]
        except Exception:
            pass
        return f"HTTP {exc.response.status_code} from provider: {body}"
    msg = str(exc).strip() or exc.__class__.__name__
    return f"{exc.__class__.__name__}: {msg}"[:300]


def _hold_still(shot: dict, anchor: Optional[Path], out_path: Path) -> Optional[Path]:
    """Build a held-still clip preserving the shot's duration so narration
    alignment is unaffected."""
    duration = float(shot["duration_seconds"])
    try:
        if anchor is not None and Path(anchor).exists():
            return ff.still_to_clip(Path(anchor), duration, out_path)
        return ff.color_clip(duration, out_path)
    except Exception:
        try:
            return ff.color_clip(duration, out_path)
        except Exception:
            return None
