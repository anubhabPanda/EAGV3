# Gemini Live (streaming voice in)

Group assignment in Session 11. Implement the realtime STT bridge
using Google's BidiGenerateContent WebSocket endpoint.

## What you build

- `adapter.py` — subclass `STTProvider`. Inside `transcribe`, open the
  WebSocket, send the `setup` frame, push the audio as a `realtimeInput`
  frame, accumulate transcript chunks until the server emits
  `turnComplete`, then close.

## Required environment

- `GEMINI_API_KEY` (the same key already used by the worker pool).

## Quirks

- The wire endpoint is
  `wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key=<KEY>`.
- The first frame must be a `BidiGenerateContentSetup` carrying the
  model name and a `responseModalities: ["AUDIO"]` / `["TEXT"]` field.
- Server response chunks may arrive interleaved with `usageMetadata`
  frames — accumulate text from `serverContent.modelTurn.parts[].text`
  and ignore everything else.
- The session has a 60-second idle timeout; close cleanly after
  `turnComplete`.

## Tests you need to pass

`tests/voice/stt/test_gemini_live.py` — six structural tests plus
`test_channel_specific_behaviour_setup_frame_first`: the adapter must
send a `BidiGenerateContentSetup` as the first frame before any audio
data. Sending audio first causes the server to reject the session.
