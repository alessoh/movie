"""Abstract adapter interfaces for every external generative service.

Concrete adapters (real or mock) implement these.  The pipeline steps only
ever talk to these interfaces, never to a concrete provider, so models and
vendors can be swapped purely through configuration.
"""
from __future__ import annotations

import abc
from pathlib import Path


class LLMProvider(abc.ABC):
    """Large language model used for condensation and shot-list passes."""

    @abc.abstractmethod
    def complete(self, system: str, prompt: str, max_tokens: int = 4000) -> str:
        """Return the model's text completion for a single prompt."""
        raise NotImplementedError


class ImageProvider(abc.ABC):
    """Still-image generator used for style and character anchor frames."""

    @abc.abstractmethod
    def generate_image(self, prompt: str, out_path: Path) -> Path:
        """Generate one image for ``prompt`` and write it to ``out_path``."""
        raise NotImplementedError


class VideoProvider(abc.ABC):
    """Image-to-video generator used for each shot clip."""

    @abc.abstractmethod
    def generate_clip(
        self,
        prompt: str,
        anchor_image: Path | None,
        duration_seconds: int,
        out_path: Path,
    ) -> Path:
        """Generate one video clip and write it to ``out_path``.

        Implementations must poll the provider's async job until the clip is
        ready (or raise on failure).  ``anchor_image`` may be ``None``.
        """
        raise NotImplementedError


class TTSProvider(abc.ABC):
    """Text-to-speech for the single narrator voice."""

    @abc.abstractmethod
    def synthesize(self, text: str, out_path: Path) -> Path:
        """Synthesize ``text`` to an audio file at ``out_path``."""
        raise NotImplementedError


class MusicProvider(abc.ABC):
    """Background-music generator for the single score track."""

    @abc.abstractmethod
    def generate_music(self, prompt: str, duration_seconds: int, out_path: Path) -> Path:
        """Generate one music track and write it to ``out_path``."""
        raise NotImplementedError
