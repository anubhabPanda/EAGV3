# ElevenLabs Flash v2.5

Group assignment in Session 11. Implement the quality-path TTS provider.

## What you build

- `adapter.py` — subclass `TTSProvider`. POST to the Flash v2.5
  endpoint and return MP3 bytes.

## Required environment

- `ELEVENLABS_API_KEY` (free tier: 10,000 chars/month).
- `ELEVENLABS_VOICE_ID` (defaults to `21m00Tcm4TlvDq8ikWAM`, Rachel).

## Quirks

- Endpoint:
  `https://api.elevenlabs.io/v1/text-to-speech/{voice_id}`.
- Auth header: `xi-api-key: <KEY>` (NOT `Authorization: Bearer`).
- Body: `{"text": "...", "model_id": "eleven_flash_v2_5"}`.
- Default output is MP3 (44.1 kHz). The free tier truncates inputs
  silently above ~5,000 chars per request; chunk before sending.

## Tests you need to pass

`tests/voice/tts/test_elevenlabs.py` — six structural tests plus
`test_channel_specific_behaviour_free_tier_quota_tracking`: the
adapter must track cumulative chars per month and fail-fast with a
429-shaped error before sending the request when the quota is
exhausted. The mock seeds the quota counter for the test.
