"""Mock-API fake for the laptop microphone (voice-first local) adapter.

Wire-format source:
  Course-defined. Audio fixtures are synthetic 16 kHz mono WAV byte
  strings constructed via Python's `wave` module. Three canned files
  cover the speech / silence / noise cases.

Inbound: an event dict `{wav_bytes, sample_rate, source: "mic"}` produced
by the adapter's recording loop after voice-activity detection.
Outbound: TTS audio bytes passed to `mock.play(bytes)`. The adapter
calls GLC's `/v1/speak`; the test patches the call.

Helpers
-------
queue_owner_message(text)         → event wrapping `hello.wav` (canned
                                    "hello" utterance) from owner
queue_stranger_message(text)      → same, from stranger
load_wav(name)                    → returns canned wav bytes for
                                    `hello.wav` / `silence.wav` / `noise.wav`
play(audio_bytes)                 → records bytes the adapter dispatched
                                    to the speaker (filled into play_log)
"""

from __future__ import annotations

import io
import math
import struct
import wave
from dataclasses import dataclass, field
from typing import Any

OWNER_LOCAL_ID = "owner"
STRANGER_LOCAL_ID = "guest"
OWNER_ID = OWNER_LOCAL_ID
STRANGER_ID = STRANGER_LOCAL_ID

SAMPLE_RATE = 16_000


def _make_wav(*, duration_s: float = 1.0, frequency: float = 220.0, amplitude: float = 0.0) -> bytes:
    """Synthesise a mono 16-bit PCM WAV. `amplitude=0` is silence,
    non-zero produces a sine tone (used for the `noise.wav` fixture)."""
    n = int(duration_s * SAMPLE_RATE)
    frames = io.BytesIO()
    with wave.open(frames, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        if amplitude == 0:
            wf.writeframes(b"\x00\x00" * n)
        else:
            samples = bytearray()
            for i in range(n):
                v = int(amplitude * 32767 * math.sin(2 * math.pi * frequency * i / SAMPLE_RATE))
                samples += struct.pack("<h", v)
            wf.writeframes(bytes(samples))
    return frames.getvalue()


CANNED_WAVS = {
    "hello.wav": _make_wav(duration_s=1.0, amplitude=0.4, frequency=180.0),
    "silence.wav": _make_wav(duration_s=1.0, amplitude=0.0),
    "noise.wav": _make_wav(duration_s=1.0, amplitude=0.05, frequency=1100.0),
}


@dataclass
class LocalMicMock:
    inbound_events: list[dict[str, Any]] = field(default_factory=list)
    send_log: list[dict[str, Any]] = field(default_factory=list)
    play_log: list[bytes] = field(default_factory=list)
    rate_limited: bool = False
    _disconnect_pending: bool = False

    def load_wav(self, name: str) -> bytes:
        if name not in CANNED_WAVS:
            raise KeyError(f"unknown canned wav: {name}")
        return CANNED_WAVS[name]

    def queue_owner_message(self, text: str = "hello") -> dict[str, Any]:
        ev = {
            "wav_bytes": self.load_wav("hello.wav"),
            "sample_rate": SAMPLE_RATE,
            "source": "mic",
            "speaker_id": OWNER_LOCAL_ID,
            "speaker_handle": "owner",
            "_synthetic_label": text,
        }
        self.inbound_events.append(ev)
        return ev

    def queue_stranger_message(self, text: str = "ping") -> dict[str, Any]:
        ev = {
            "wav_bytes": self.load_wav("hello.wav"),
            "sample_rate": SAMPLE_RATE,
            "source": "mic",
            "speaker_id": STRANGER_LOCAL_ID,
            "speaker_handle": "stranger",
            "_synthetic_label": text,
        }
        self.inbound_events.append(ev)
        return ev

    def queue_silence(self) -> dict[str, Any]:
        ev = {
            "wav_bytes": self.load_wav("silence.wav"),
            "sample_rate": SAMPLE_RATE,
            "source": "mic",
            "speaker_id": OWNER_LOCAL_ID,
            "speaker_handle": "owner",
        }
        self.inbound_events.append(ev)
        return ev

    async def play(self, audio_bytes: bytes) -> None:
        self.play_log.append(audio_bytes)

    async def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.rate_limited:
            return {"status": 429, "error": "tts rate limit"}
        self.send_log.append(payload)
        if isinstance(payload, dict) and payload.get("audio_bytes"):
            await self.play(payload["audio_bytes"])
        return {"status": 200, "id": f"play-{len(self.send_log)}"}

    def force_disconnect(self) -> None:
        self._disconnect_pending = True

    def pop_disconnect(self) -> bool:
        was = self._disconnect_pending
        self._disconnect_pending = False
        return was
