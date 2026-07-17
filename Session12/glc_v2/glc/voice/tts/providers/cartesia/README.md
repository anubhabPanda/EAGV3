# Cartesia Sonic (streaming)

Group assignment in Session 11. Implement the streaming-path TTS
provider — the use case is sub-second time-to-first-audio for
real-time phone calls (Twilio Voice outbound) and the WebUI voice
mode.

## What you build

- `adapter.py` — subclass `TTSProvider`. The synchronous
  `synthesize()` method blocks until the full audio arrives; a future
  PR adds a streaming chunked variant. For S11, focus on minimal
  TTFA: a fast non-streaming Sonic request.

## Required environment

- `CARTESIA_API_KEY`.
- `CARTESIA_VOICE_ID` (defaults to a documented "neutral" voice id).

## Quirks

- Endpoint: `https://api.cartesia.ai/tts/bytes`.
- Required header: `Cartesia-Version: 2025-04-16`.
- Body specifies the model (`sonic-2`), the voice config (`{mode: "id",
  id: ...}`), and the output format (PCM 16-bit @ 24 kHz mono in a
  WAV container).
- The bytes endpoint is the non-streaming variant; the streaming WS
  endpoint lives at `wss://api.cartesia.ai/tts/websocket` and is out
  of scope here.

## Tests you need to pass

`tests/voice/tts/test_cartesia.py` — six structural tests plus
`test_channel_specific_behaviour_time_to_first_audio`: the mock
records the timestamp of the first byte delivered. The adapter must
not buffer the entire response — it should return as soon as the
first audio chunk is available. The test asserts the recorded TTFA
is under a synthetic threshold (50ms against the mock).
