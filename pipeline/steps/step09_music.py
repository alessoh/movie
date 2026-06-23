"""Step 9 - Music bed.

Generate one background track roughly the length of the movie whose mood
matches the logline.  If the music fails after retries, the film proceeds with
no music (section 9).  Returns a Path or None.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from config import settings
from pipeline.providers.base import MusicProvider


def generate_music(
    music: MusicProvider,
    shot_list: dict,
    total_duration: float,
    work_dir: Path,
) -> Optional[Path]:
    out_path = work_dir / "music.mp3"
    logline = shot_list.get("logline", "")
    style = shot_list.get("style_prompt", "")
    prompt = (
        f"Instrumental cinematic score, no vocals, that underscores this film: "
        f"{logline}. Mood and palette: {style}."
    )
    duration = max(30, int(total_duration) + 4)

    attempts = settings.max_retries_per_shot + 1
    for attempt in range(attempts):
        try:
            music.generate_music(prompt, duration, out_path)
            if out_path.exists() and out_path.stat().st_size > 0:
                return out_path
        except Exception:
            pass
        if attempt < attempts - 1:
            time.sleep(2 * (attempt + 1))
    return None
