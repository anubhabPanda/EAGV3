"""Configuration and environment variable loader for the Groq Whisper STT provider."""

from __future__ import annotations

import os

DEFAULT_MODEL = "whisper-large-v3-turbo"


def load_config(config_dict: dict) -> tuple[str, str]:
    """Load the target API key and model identifier."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise NotImplementedError("GROQ_API_KEY environment variable is not set")

    model = os.getenv("GLC_GROQ_STT_MODEL") or config_dict.get("model") or DEFAULT_MODEL
    return api_key, model
