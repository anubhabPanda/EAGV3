"""Channel-specific Pydantic types for the Cartesia TTS provider.

This module is the single source of truth for everything specific to
Cartesia's wire format: the endpoint URL, the request body shape, the
required headers, and the few constants (mime type, sample rate,
default voice) the adapter needs but shouldn't hardcode inline.

Kept deliberately separate from `adapter.py` so the *what does
Cartesia expect on the wire* knowledge lives in one typed, testable
place, and `adapter.py` only orchestrates *when* to call it (mock vs.
live, error mapping, streaming consumption).

Wire-format source: https://docs.cartesia.ai/api-reference/tts/bytes
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Cartesia's non-streaming TTS endpoint. The streaming variant lives at
#: wss://api.cartesia.ai/tts/websocket and is out of scope for this
#: synchronous synthesize() contract -- see provider README.
CARTESIA_ENDPOINT = "https://api.cartesia.ai/tts/bytes"

#: Cartesia API version pin. Required header; omitting it is rejected by
#: the API outright rather than silently falling back to a default.
CARTESIA_API_VERSION = "2025-04-16"

#: Model id used for every request. "sonic-2" is Cartesia's
#: low-latency-tier model, matching this slot's purpose (sub-second
#: time-to-first-audio for live calls and WebUI voice mode).
DEFAULT_MODEL_ID = "sonic-2"

#: Output format requested from Cartesia: 16-bit PCM in a WAV container
#: at 24kHz mono. Matches what `DEFAULT_MIME` / `DEFAULT_SAMPLE_RATE`
#: below describe, so the three stay in lockstep.
OUTPUT_CONTAINER = "wav"
OUTPUT_ENCODING = "pcm_s16le"
DEFAULT_SAMPLE_RATE = 24000

#: Mime type reported on the returned SynthesizeResult. Must match
#: OUTPUT_CONTAINER above -- if that ever changes to "raw" or "mp3",
#: this needs to change with it.
DEFAULT_MIME = "audio/wav"

#: Documented "neutral" Cartesia voice id, used when neither the caller
#: nor CARTESIA_VOICE_ID supplies one. Keeping a real fallback here
#: means synthesize() never needs a voice id to produce *some* audio.
DEFAULT_VOICE_ID = "a0e99841-438c-4a64-b679-ae501e7d6091"


# ---------------------------------------------------------------------------
# Request body types
# ---------------------------------------------------------------------------


class CartesiaVoiceConfig(BaseModel):
    """The `voice` object in a Cartesia `/tts/bytes` request body.

    Cartesia supports other `mode` values (e.g. raw embeddings); this
    adapter only ever selects by id, so `mode` is fixed rather than a
    field -- there is nothing for a caller to misconfigure.

    `id` is typed `str` (matching `synthesize()`'s own `voice_id: str |
    None` parameter and `resolve_voice_id()`'s return type -- see
    base.py and resolve_voice_id() below), but validated at runtime to
    require UUID shape. Every real Cartesia voice id is a UUID; the
    stricter runtime check catches a common copy-paste mistake (e.g. a
    literal "<your voice id>" placeholder left over from a curl
    example, or stray whitespace) before it costs a network round-trip,
    rather than only catching it when Cartesia rejects the request.
    Keeping the *static* type as `str` (instead of pydantic's `UUID4`,
    which mypy sees as `uuid.UUID`) avoids a type mismatch at the call
    site in `adapter.py`, where the value in hand is always a `str`.
    """

    model_config = ConfigDict(extra="forbid")

    mode: Literal["id"] = "id"
    id: str

    @field_validator("id")
    @classmethod
    def _id_is_uuid_shaped(cls, value: str) -> str:
        try:
            UUID(value)
        except ValueError as exc:
            raise ValueError(f"voice id must be a valid UUID, got {value!r}") from exc
        return value


class CartesiaOutputFormat(BaseModel):
    """The `output_format` object in a Cartesia `/tts/bytes` request body.

    Fixed to the WAV/PCM16/24kHz combination this adapter is built
    around (see OUTPUT_CONTAINER / OUTPUT_ENCODING / DEFAULT_SAMPLE_RATE
    above) -- there is exactly one shape `adapter.py` knows how to label
    correctly on the returned SynthesizeResult, so this type encodes
    that shape rather than exposing knobs nothing else uses yet.
    """

    model_config = ConfigDict(extra="forbid")

    container: str = OUTPUT_CONTAINER
    encoding: str = OUTPUT_ENCODING
    sample_rate: int = Field(default=DEFAULT_SAMPLE_RATE, gt=0)


class CartesiaTTSRequest(BaseModel):
    """Full JSON body for `POST https://api.cartesia.ai/tts/bytes`.

    `adapter.py` constructs one of these per call and serializes it
    with `.to_payload()` for `httpx`'s `json=` argument. Validation
    here (e.g. rejecting an empty transcript, rejecting a malformed
    voice id) catches a bad request before it's sent, rather than
    letting Cartesia reject it and the adapter having to interpret a
    400 it could have avoided.
    """

    model_config = ConfigDict(extra="forbid")

    transcript: str = Field(..., min_length=1)
    voice: CartesiaVoiceConfig
    model_id: str = DEFAULT_MODEL_ID
    output_format: CartesiaOutputFormat = Field(default_factory=CartesiaOutputFormat)

    def to_payload(self) -> dict[str, object]:
        """Serialize to the exact dict shape Cartesia's API expects.

        Uses Pydantic's own `model_dump()` rather than a hand-written
        field-by-field dict, so adding a field to any of the nested
        models above is automatically reflected here -- there is no
        second place that can fall out of sync with the schema.
        """
        return self.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Helpers used directly by adapter.py
# ---------------------------------------------------------------------------


def build_headers(api_key: str) -> dict[str, str]:
    """Build the required headers for a Cartesia `/tts/bytes` call.

    `X-API-Key` matches both the course-documented quirk for this slot
    and the behavior of Cartesia's own official SDK (`Authorization:
    Bearer <token>` is also accepted by the raw HTTP API). `Cartesia-
    Version` is always sent, pinned to CARTESIA_API_VERSION, so this
    adapter's behavior can't silently drift if Cartesia changes its
    default. NOTE: at the pinned 2025-04-16 version, Cartesia's error
    responses are plain text ("Title: Message"), not JSON -- that
    changed to a structured JSON error envelope only from the
    2026-03-01 version onward. `adapter.py`'s plain-text error handling
    is therefore correct for this pin; if the version pin above is ever
    bumped past 2026-03-01, error parsing needs to change too.
    """
    if not api_key:
        raise ValueError("api_key must be non-empty")
    return {
        "X-API-Key": api_key,
        "Cartesia-Version": CARTESIA_API_VERSION,
        "Content-Type": "application/json",
    }


def resolve_voice_id(explicit_voice_id: str | None, env_voice_id: str | None) -> str:
    """Resolve which voice id to actually send upstream, as a string.

    Precedence: explicit argument to `synthesize()` > `CARTESIA_VOICE_ID`
    env var > documented default. This means a caller never has to know
    a real Cartesia voice id just to get *some* audio out, while still
    being able to override per call.

    Returns a plain `str`, not a `UUID` -- `synthesize()`'s own
    `voice_id` parameter is typed `str | None` (see `base.py`), so this
    function's signature matches the type it's actually fed from. The
    returned string is *not* guaranteed to be UUID-shaped at this
    point: `CartesiaVoiceConfig(id=...)` performs that check one step
    later, at request-construction time. Passing a malformed id here is
    intentionally not an error in this function -- it becomes one only
    when the request is actually built, which is where a clear
    `ValidationError` pointing at the `voice.id` field is more useful
    than one raised deep inside voice resolution.
    """
    if explicit_voice_id:
        return explicit_voice_id
    if env_voice_id:
        return env_voice_id
    return DEFAULT_VOICE_ID
