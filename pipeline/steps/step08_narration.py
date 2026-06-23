"""Step 8 - Narration voice.

For each (non-dropped) shot, synthesize its narration sentence with the single
configured narrator voice.  A narration line that fails after retries leaves
that shot with no narration rather than blocking the film.

Mutates each clip-result dict in place, adding ``narration_audio`` (Path|None).
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, List, Optional

from config import settings
from pipeline.providers.base import TTSProvider

ProgressFn = Callable[[int, int, str], None]


def generate_narration(
    tts: TTSProvider,
    clip_results: List[dict],
    work_dir: Path,
    progress: Optional[ProgressFn] = None,
) -> List[dict]:
    narr_dir = work_dir / "narration"
    narr_dir.mkdir(parents=True, exist_ok=True)
    active = [r for r in clip_results if not r.get("dropped")]
    total = len(active)

    for n, r in enumerate(active, start=1):
        shot = r["shot"]
        text = (shot.get("narration") or "").strip()
        r["narration_audio"] = None
        if not text:
            continue
        if progress:
            progress(n, total, f"Recording narration {n} of {total}")
        out_path = narr_dir / f"narr_{shot['index']:02d}.mp3"
        audio = _synthesize_with_retry(tts, text, out_path)
        if audio is None and progress:
            progress(n, total, f"Narration for shot {shot['index']} failed; shot will be silent.")
        r["narration_audio"] = audio
    return clip_results


def _synthesize_with_retry(tts: TTSProvider, text: str, out_path: Path) -> Optional[Path]:
    attempts = settings.max_retries_per_shot + 1
    for attempt in range(attempts):
        try:
            tts.synthesize(text, out_path)
            if out_path.exists() and out_path.stat().st_size > 0:
                return out_path
        except Exception:
            pass
        if attempt < attempts - 1:
            time.sleep(1.5 * (attempt + 1))
    return None
