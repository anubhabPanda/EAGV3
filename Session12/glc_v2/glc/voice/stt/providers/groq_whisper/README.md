# Groq Whisper Large v3 Turbo

This is a **group assignment** in Session 11. Implement the Groq STT
provider to make the seven tests at `tests/voice/stt/test_groq_whisper.py`
pass.

## What you build

Two files under this directory:

- `adapter.py` — subclass `glc.voice.stt.base.STTProvider` and implement
  `transcribe(audio_bytes, mime) -> TranscribeResult`.
- `schemas.py` — Pydantic types you need (rare for STT; usually empty).

## Required environment variables

- `GROQ_API_KEY` — free sign-up at https://console.groq.com.

## Free-tier limits

Thousands of audio-minutes per month for unverified accounts. Verified
accounts get higher limits. The LPU hardware delivers sub-second latency
on short clips.

## Wire-format quirks

- The endpoint is `https://api.groq.com/openai/v1/audio/transcriptions`.
  It is OpenAI-compatible — multipart/form-data with `file` and `model`.
- Default model: `whisper-large-v3-turbo` (env override:
  `GLC_GROQ_STT_MODEL`).
- `response_format=verbose_json` to get the language code and duration.
- 25 MB upload cap. Longer audio must be chunked client-side.

## Tests you need to pass

The failing tests live at `tests/voice/stt/test_groq_whisper.py`. Six
structural tests + one behavioural test (`test_channel_specific_behaviour_openai_multipart_shape`)
that asserts the dispatched HTTP body is OpenAI-format multipart with
`model` set, not arbitrary JSON.

The mock-API fake at `tests/voice/stt/mocks/groq_whisper_mock.py` is
your contract surface. Do **not** edit the mock or the test file.
