"""TTS facade. Provider catalogue under `providers/<name>/`."""

from glc.voice.tts.base import SynthesizeResult, TTSError, TTSProvider
from glc.voice.tts.router import synthesize

__all__ = ["SynthesizeResult", "TTSError", "TTSProvider", "synthesize"]
