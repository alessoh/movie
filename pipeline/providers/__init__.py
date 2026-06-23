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
    from .music_aggregator import AggregatorMusicProvider
    from .tts_elevenlabs import ElevenLabsTTSProvider
    from .video_aggregator import AggregatorVideoProvider

    llm = _build_llm(settings.llm_provider)
    image = AggregatorImageProvider()
    video = AggregatorVideoProvider()
    tts = ElevenLabsTTSProvider()
    music = AggregatorMusicProvider()
    return ProviderBundle(llm=llm, image=image, video=video, tts=tts, music=music)


def _build_llm(provider: str) -> LLMProvider:
    """Select the language-model adapter from ``LLM_PROVIDER``.

    Adding a new LLM vendor is just a new adapter implementing ``LLMProvider``
    plus one line here -- no pipeline step changes.
    """
    name = (provider or "anthropic").lower()
    if name == "anthropic":
        from .llm_anthropic import AnthropicLLMProvider

        return AnthropicLLMProvider()
    if name == "gemini":
        from .llm_gemini import GeminiLLMProvider

        return GeminiLLMProvider()
    if name == "openai":
        from .llm_openai import OpenAILLMProvider

        return OpenAILLMProvider()
    raise RuntimeError(
        f"Unknown LLM_PROVIDER '{provider}'. Supported: anthropic, gemini, openai."
    )
