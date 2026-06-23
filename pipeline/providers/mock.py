"""Mock implementations of every provider adapter.

Selected by ``RUN_MODE=mock``.  These produce real, valid media files (via
FFmpeg and Pillow-free PPM/PNG generation) so the full pipeline -- including
orchestration, progress reporting, FFmpeg assembly and the UI -- can be
exercised end to end in seconds for free, with no API keys and no cost.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .base import ImageProvider, LLMProvider, MusicProvider, TTSProvider, VideoProvider

# A deterministic palette so successive shots look visibly different.
_COLORS = [
    "0x1f3a5f", "0x5f1f3a", "0x3a5f1f", "0x5f3a1f", "0x1f5f5f",
    "0x3a1f5f", "0x5f5f1f", "0x2f4f4f", "0x4f2f4f", "0x4f4f2f",
    "0x223344", "0x443322", "0x334422", "0x224433", "0x332244",
    "0x445566",
]


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {' '.join(cmd)}\n{proc.stderr[-800:]}")


class MockLLMProvider(LLMProvider):
    """Returns a small fixed beats/shot-list payload regardless of input."""

    def complete(self, system: str, prompt: str, max_tokens: int = 4000) -> str:
        lowered = (system + prompt).lower()
        # Shot-list pass: the prompt mentions "shot list" / JSON schema.
        if "shot" in lowered and ("json" in lowered or "shots" in lowered):
            return json.dumps(self._shot_list())
        # Condensation pass: return beats JSON.
        return json.dumps(self._beats())

    @staticmethod
    def _beats() -> dict:
        beats = [
            {"index": i + 1, "moment": f"Mock story beat number {i + 1}."}
            for i in range(15)
        ]
        return {
            "title": "The Mock Chronicle",
            "logline": "A test hero journeys through a deterministic world to prove the pipeline works.",
            "beats": beats,
        }

    @staticmethod
    def _shot_list() -> dict:
        shots = []
        for i in range(15):
            shots.append(
                {
                    "index": i + 1,
                    "duration_seconds": 8,
                    "visual_prompt": f"Mock visual for shot {i + 1}, a wide cinematic frame.",
                    "narration": f"In the {_ordinal(i + 1)} moment, our hero presses onward.",
                    "character_ids": ["c1"],
                }
            )
        return {
            "title": "The Mock Chronicle",
            "logline": "A test hero journeys through a deterministic world to prove the pipeline works.",
            "style_prompt": "muted teal-and-amber palette, soft cinematic lighting, painterly mood",
            "characters": [
                {"id": "c1", "name": "The Hero", "appearance_prompt": "a weathered traveler in a grey cloak"}
            ],
            "shots": shots,
        }


def _ordinal(n: int) -> str:
    words = [
        "first", "second", "third", "fourth", "fifth", "sixth", "seventh",
        "eighth", "ninth", "tenth", "eleventh", "twelfth", "thirteenth",
        "fourteenth", "fifteenth", "sixteenth",
    ]
    return words[n - 1] if 1 <= n <= len(words) else f"{n}th"


class MockImageProvider(ImageProvider):
    """Generates a simple solid-color PNG via FFmpeg's color source."""

    def generate_image(self, prompt: str, out_path: Path) -> Path:
        color = _COLORS[abs(hash(prompt)) % len(_COLORS)]
        _run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"color=c={color}:s=1280x720:d=1",
                "-frames:v", "1",
                str(out_path),
            ]
        )
        return out_path


class MockVideoProvider(VideoProvider):
    """Generates a short solid-color clip of the requested duration."""

    def generate_clip(self, prompt, anchor_image, duration_seconds, out_path) -> Path:
        color = _COLORS[abs(hash(prompt)) % len(_COLORS)]
        d = max(1, int(duration_seconds))
        _run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"color=c={color}:s=1280x720:r=24:d={d}",
                "-f", "lavfi",
                "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
                "-t", str(d),
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-shortest",
                str(out_path),
            ]
        )
        return out_path


class MockTTSProvider(TTSProvider):
    """Generates a short, quiet tone whose length scales with the text."""

    def synthesize(self, text: str, out_path: Path) -> Path:
        # ~0.06s per word, clamped to a sensible spoken-line range.
        words = max(1, len(text.split()))
        duration = min(8.0, max(1.5, words * 0.4))
        _run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"sine=frequency=220:duration={duration:.2f}",
                "-af", "volume=0.15",
                "-c:a", "libmp3lame",  # narration paths use .mp3 (matches ElevenLabs)
                str(out_path),
            ]
        )
        return out_path


class MockMusicProvider(MusicProvider):
    """Generates a quiet silent-ish track of the requested length."""

    def generate_music(self, prompt: str, duration_seconds: int, out_path: Path) -> Path:
        d = max(1, int(duration_seconds))
        _run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-t", str(d),
                "-c:a", "libmp3lame",  # music path uses .mp3
                str(out_path),
            ]
        )
        return out_path
