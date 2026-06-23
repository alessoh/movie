"""Provider adapters.

Every external generative service sits behind one of the abstract interfaces
in ``base.py`` so models can be swapped via configuration.  ``get_providers``
returns a bundle of concrete adapters chosen from ``config.settings`` (or the
mock adapters when ``RUN_MODE=mock``).
"""
from __future__ import annotations

from dataclasses import dataclass

from config import settings

from .base import ImageProvider, LLMProvider, MusicProvider, TTSProvider, VideoProvider


@dataclass
class ProviderBundle:
    llm: LLMProvider
    image: ImageProvider
    video: VideoProvider
    tts: TTSProvider
    music: MusicProvider


def get_providers() -> ProviderBundle:
    """Construct the provider bundle for the current run mode."""
    if settings.is_mock:
        from .mock import (
            MockImageProvider,
            MockLLMProvider,
            MockMusicProvider,
            MockTTSProvider,
            MockVideoProvider,
        )

        return ProviderBundle(
            llm=MockLLMProvider(),
            image=MockImageProvider(),
            video=MockVideoProvider(),
            tts=MockTTSProvider(),
            music=MockMusicProvider(),
        )

    # --- REAL providers -----------------------------------------------------
    from .images_aggregator import AggregatorImageProvider
    from .llm_anthropic import AnthropicLLMProvider
    from .music_aggregator import AggregatorMusicProvider
    from .tts_elevenlabs import ElevenLabsTTSProvider
    from .video_aggregator import AggregatorVideoProvider

    llm = AnthropicLLMProvider()
    image = AggregatorImageProvider()
    video = AggregatorVideoProvider()
    tts = ElevenLabsTTSProvider()
    music = AggregatorMusicProvider()
    return ProviderBundle(llm=llm, image=image, video=video, tts=tts, music=music)
