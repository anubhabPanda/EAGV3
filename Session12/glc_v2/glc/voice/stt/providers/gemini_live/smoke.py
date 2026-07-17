"""Real-API smoke runner for the Gemini Live STT provider.

This is a *manual* end-to-end check that exercises the real Gemini Live
WebSocket path (the one CI never runs). Use it before recording a demo or
after merging changes to confirm the adapter still returns a single, clean
transcript against the live service.

It is intentionally NOT a pytest test: ``testpaths = ["tests"]`` means it is
never collected by the suite, and ``glc/voice/stt/providers/*`` is omitted
from coverage. Running it requires a real ``GEMINI_API_KEY`` and network
access, so it stays out of the automated gate on purpose.

Usage (from the repo root)::

    uv run python -m glc.voice.stt.providers.gemini_live.smoke
    uv run python -m glc.voice.stt.providers.gemini_live.smoke "Custom phrase"
    uv run python -m glc.voice.stt.providers.gemini_live.smoke --wav path/to/16k_mono.wav
    uv run python -m glc.voice.stt.providers.gemini_live.smoke --mic --seconds 5

The API key is read from the environment, falling back to a ``.env`` file in
this provider folder (``GEMINI_API_KEY=...``). The ``.env`` is gitignored.

Audio source:
  * Default: synthesise the phrase with macOS ``say`` + ``afconvert`` into
    16 kHz mono PCM.
  * ``--wav``: read an existing 16 kHz mono WAV file instead (works on any OS).
  * ``--mic``: prompt you to speak and record live from the microphone. Needs
    the optional ``sounddevice`` package (``uv pip install sounddevice``); it
    is intentionally not a project dependency.

Exit code is ``0`` on a successful, non-duplicated transcript and non-zero
otherwise, so it can double as a simple smoke gate in a manual checklist.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
import wave
from pathlib import Path

from glc.voice.stt.providers.gemini_live.adapter import Provider

_PROVIDER_DIR = Path(__file__).resolve().parent
_ENV_FILE = _PROVIDER_DIR / ".env"
_DEFAULT_PHRASE = "Hello, this is a Gemini Live smoke test."
_PCM_MIME = "audio/pcm;rate=16000"
_SAMPLE_RATE = 16000
_DEFAULT_MIC_SECONDS = 5


def _load_api_key() -> str:
    """Return GEMINI_API_KEY from the environment or the provider ``.env``."""
    if not os.environ.get("GEMINI_API_KEY") and _ENV_FILE.exists():
        for line in _ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key or "your-gemini" in api_key:
        sys.exit(f"GEMINI_API_KEY is not set. Export it or add it to {_ENV_FILE} (this file is gitignored).")
    return api_key


def _read_wav_pcm(path: Path) -> bytes:
    """Read raw PCM frames from a 16 kHz mono WAV file."""
    with wave.open(str(path), "rb") as wav:
        if wav.getframerate() != 16000 or wav.getnchannels() != 1:
            sys.exit(
                f"{path} must be 16 kHz mono WAV "
                f"(got {wav.getframerate()} Hz, {wav.getnchannels()} channel(s))."
            )
        return wav.readframes(wav.getnframes())


def _synthesize_pcm(phrase: str) -> bytes:
    """Synthesise ``phrase`` to 16 kHz mono PCM via macOS ``say``/``afconvert``."""
    if not (shutil.which("say") and shutil.which("afconvert")):
        sys.exit("macOS 'say'/'afconvert' not found. Pass --wav with a 16 kHz mono WAV file instead.")
    aiff = _PROVIDER_DIR / "_smoke_say.aiff"
    wav = _PROVIDER_DIR / "_smoke_say.wav"
    try:
        subprocess.run(["say", "-o", str(aiff), phrase], check=True)
        subprocess.run(
            ["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(aiff), str(wav)],
            check=True,
        )
        return _read_wav_pcm(wav)
    finally:
        aiff.unlink(missing_ok=True)
        wav.unlink(missing_ok=True)


def _record_mic(seconds: int) -> bytes:
    """Prompt the user to speak, record ``seconds`` of 16 kHz mono PCM.

    ``sounddevice`` is imported lazily so it stays an optional extra (it is
    deliberately not a project dependency). Install it locally with
    ``uv pip install sounddevice`` to use ``--mic``.
    """
    try:
        import sounddevice as sd
    except ImportError:
        sys.exit(
            "The 'sounddevice' package is required for --mic. "
            "Install it locally with: uv pip install sounddevice"
        )
    input(f"Press Enter, then speak for {seconds} seconds... ")
    print("🎤 Recording — speak now!")
    frames = sd.rec(int(seconds * _SAMPLE_RATE), samplerate=_SAMPLE_RATE, channels=1, dtype="int16")
    sd.wait()
    print("✅ Done recording. Sending to Gemini Live...")
    return bytes(frames.tobytes())


def _looks_duplicated(text: str) -> bool:
    """Heuristic: detect the old bug where the sentence was emitted twice."""
    cleaned = text.strip().rstrip(".")
    if not cleaned:
        return False
    half = len(cleaned) // 2
    first, second = cleaned[:half].strip(), cleaned[half:].strip()
    return bool(first) and first == second


async def _run(audio: bytes) -> tuple[bool, str]:
    """Transcribe ``audio`` and return (passed, summary)."""
    result = await Provider().transcribe(audio, _PCM_MIME)
    lines = [
        "-- RESULT --",
        f"text     : {result.text!r}",
        f"language : {result.language}",
        f"duration : {result.duration_ms} ms",
        f"provider : {result.provider}",
    ]
    passed = bool(result.text.strip()) and not _looks_duplicated(result.text)
    return passed, "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gemini Live STT real-API smoke runner.")
    parser.add_argument("phrase", nargs="*", help="phrase to synthesise and transcribe")
    parser.add_argument("--wav", type=Path, help="use this 16 kHz mono WAV instead of 'say'")
    parser.add_argument("--mic", action="store_true", help="record from the microphone and transcribe")
    parser.add_argument(
        "--seconds", type=int, default=_DEFAULT_MIC_SECONDS, help="seconds to record with --mic"
    )
    args = parser.parse_args(argv)

    _load_api_key()

    if args.mic:
        audio = _record_mic(args.seconds)
        source = f"mic: {args.seconds}s"
    elif args.wav:
        audio = _read_wav_pcm(args.wav)
        source = str(args.wav)
    else:
        phrase = " ".join(args.phrase) or _DEFAULT_PHRASE
        audio = _synthesize_pcm(phrase)
        source = f"say: {phrase!r}"

    print(f"audio    : {len(audio)} bytes raw PCM 16 kHz mono ({source})")
    passed, summary = asyncio.run(_run(audio))
    print(summary)
    print("SMOKE: PASS" if passed else "SMOKE: FAIL (empty or duplicated transcript)")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
