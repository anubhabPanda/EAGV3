"""Local Kokoro-82M inference shim.

Kokoro is shipped under ~/.glc/models/kokoro-82M/. First call lazy-loads
the model; the loaded pipeline is reused. CI skips the first-call download
via the `requires_models` pytest marker.

The actual model loader is delegated to the `kokoro` PyPI package. We
import it inside the function so the gateway boot does not pay the
import cost on installs that don't use TTS.
"""

from __future__ import annotations

import os
from pathlib import Path

MODEL_DIR = Path(os.path.expanduser(os.getenv("GLC_KOKORO_MODEL_DIR", "~/.glc/models/kokoro-82M")))

_pipeline = None


def _load():
    global _pipeline
    if _pipeline is not None:
        return _pipeline
    try:
        from kokoro import KPipeline  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "kokoro package not installed. Run `uv pip install kokoro` "
            "or use prefer='fallback' for system TTS."
        ) from e
    _pipeline = KPipeline(lang_code="a")
    return _pipeline


def synthesize(text: str, voice_id: str = "af_bella") -> tuple[bytes, int]:
    """Returns (wav_bytes, sample_rate). 24kHz mono."""
    import io
    import wave

    import numpy as np  # type: ignore

    pipeline = _load()
    generator = pipeline(text, voice=voice_id, speed=1.0)
    chunks = []
    for _, _, audio in generator:
        if hasattr(audio, "numpy"):
            audio = audio.numpy()
        chunks.append(np.asarray(audio, dtype=np.float32))
    if not chunks:
        return b"", 24000
    waveform = np.concatenate(chunks)
    pcm = (waveform * 32767.0).clip(-32768, 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue(), 24000
