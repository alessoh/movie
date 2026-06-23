"""Thin wrappers around FFmpeg/FFprobe used by several steps."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

# Canonical video format every clip is normalized to before concatenation.
WIDTH = 1280
HEIGHT = 720
FPS = 24
SAMPLE_RATE = 44100

# x264 speed/quality trade-off. "veryfast" keeps mock runs quick while still
# producing good-looking real output; override with X264_PRESET if desired.
import os as _os

X264_PRESET = _os.environ.get("X264_PRESET", "veryfast")


def run_ffmpeg(args: list[str], timeout: int = 600) -> None:
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed (exit {proc.returncode}):\n"
            f"cmd: {' '.join(cmd)}\n{proc.stderr[-1500:]}"
        )


def probe_duration(path: Path) -> float:
    """Return media duration in seconds (0.0 if unknown)."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json", str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return 0.0
    try:
        return float(json.loads(proc.stdout)["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError):
        return 0.0


def has_audio(path: Path) -> bool:
    """Return True if the media file contains at least one audio stream."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=index",
        "-of", "json", str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return False
    try:
        return bool(json.loads(proc.stdout).get("streams"))
    except json.JSONDecodeError:
        return False


def still_to_clip(image_path: Path, duration: float, out_path: Path) -> Path:
    """Make a silent video clip that holds a still image for ``duration`` s."""
    run_ffmpeg(
        [
            "-loop", "1",
            "-i", str(image_path),
            "-f", "lavfi",
            "-i", f"anullsrc=channel_layout=stereo:sample_rate={SAMPLE_RATE}",
            "-t", f"{duration:.2f}",
            "-r", str(FPS),
            "-vf", f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
                   f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1",
            "-c:v", "libx264", "-preset", X264_PRESET, "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-shortest",
            str(out_path),
        ]
    )
    return out_path


def color_clip(duration: float, out_path: Path, color: str = "0x202020") -> Path:
    """Last-resort placeholder: a solid color clip of the given duration."""
    run_ffmpeg(
        [
            "-f", "lavfi", "-i", f"color=c={color}:s={WIDTH}x{HEIGHT}:r={FPS}:d={duration:.2f}",
            "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate={SAMPLE_RATE}",
            "-t", f"{duration:.2f}",
            "-c:v", "libx264", "-preset", X264_PRESET, "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest",
            str(out_path),
        ]
    )
    return out_path


def normalize_clip(in_path: Path, duration: float, out_path: Path) -> Path:
    """Re-encode any clip to the canonical resolution/fps/format and exact
    duration so concatenation joins cleanly."""
    run_ffmpeg(
        [
            "-i", str(in_path),
            "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate={SAMPLE_RATE}",
            "-t", f"{duration:.2f}",
            "-map", "0:v:0", "-map", "1:a:0",
            "-vf", f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
                   f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={FPS}",
            "-c:v", "libx264", "-preset", X264_PRESET, "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-shortest",
            str(out_path),
        ]
    )
    return out_path
