"""Twilio path tests — Phase 1 (helper unit tests) and Phase 2 (orchestrators).

Phase 1:
    US-6: verify_twilio_signature  (HMAC-SHA1, X-Twilio-Signature)
    US-7: parse_twilio_payload     (form-urlencoded inbound fields)
    US-8: build_twilio_send_payload (outbound form body)

Phase 2:
    US-9/10: on_message + send orchestrators (dual-provider, provider cache,
             Meta-131030 fallback to Twilio, outbound guard)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import patch
from urllib.parse import urlencode

import pytest
from twilio.request_validator import RequestValidator

from glc.channels.catalogue.whatsapp.adapter import (
    Adapter,
    _headers,
    _is_meta_131030,
    _send_meta,
    _send_twilio,
    build_twilio_send_payload,
    parse_twilio_payload,
    provider_cache,
    verify_twilio_signature,
)
from glc.channels.catalogue.whatsapp.schemas import (
    MetaSendPayload,
    MetaSendText,
    TwilioSendPayload,
)
from glc.channels.envelope import ChannelReply
from glc.security.pairing import get_pairing_store
from tests.channels.mocks.whatsapp_mock import OWNER_ID, STRANGER_ID, WhatsappMock


@pytest.fixture(autouse=True)
def _clear_provider_cache():
    provider_cache.clear()
    yield
    provider_cache.clear()


@pytest.fixture(autouse=True)
def _isolated_glc_state(monkeypatch, tmp_path):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    monkeypatch.setenv("GLC_CONFIG_DIR", str(cfg))
    monkeypatch.setenv("GLC_AUDIT_DB", str(tmp_path / "audit.sqlite"))
    monkeypatch.setenv("GLC_PAIRING_DB", str(tmp_path / "pairings.sqlite"))
    monkeypatch.setenv("GLC_GATEWAY_DB", str(tmp_path / "gateway.sqlite"))

    import glc.config as _cfg

    _cfg.CONFIG_DIR = cfg
    import glc.security.pairing as _p

    _p._singleton = None
    import glc.security.rate_limits as _r

    _r._limiter = None
    import glc.policy.engine as _e

    _e._engine = None
    import glc.audit.store as _a

    _a._singleton = None
    yield


# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

WEBHOOK_URL = "https://example.ngrok.io/whatsapp/inbound"
AUTH_TOKEN = "test_auth_token_abc123"

# Confirmed Twilio inbound field set (HANDOFF §0.1, §7.7)
SAMPLE_PAYLOAD: dict = {
    "MessageSid": "SM1234567890abcdef1234567890abcdef",
    "AccountSid": "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "From": "whatsapp:+14155238886",
    "To": "whatsapp:+14155551234",
    "Body": "Hello from Twilio sandbox",
    "NumMedia": "0",
    "ProfileName": "Test User",
    "WaId": "14155238886",
    "ApiVersion": "2010-04-01",
}

RECEIVED_AT = datetime(2026, 6, 27, 10, 0, 0, tzinfo=UTC)

BOT_PHONE = "+14155551234"
RECIPIENT_PHONE = "14155238886"


def _make_signature(url: str, params: dict, token: str) -> str:
    return RequestValidator(token).compute_signature(url, params)


# ---------------------------------------------------------------------------
# US-6: verify_twilio_signature
# ---------------------------------------------------------------------------


def test_verify_twilio_signature_valid():
    sig = _make_signature(WEBHOOK_URL, SAMPLE_PAYLOAD, AUTH_TOKEN)
    assert verify_twilio_signature(WEBHOOK_URL, SAMPLE_PAYLOAD, sig, AUTH_TOKEN) is True


def test_verify_twilio_signature_wrong_signature():
    assert verify_twilio_signature(WEBHOOK_URL, SAMPLE_PAYLOAD, "wrong_sig", AUTH_TOKEN) is False


def test_verify_twilio_signature_tampered_params():
    """Valid sig computed for original params must not pass after params are changed."""
    sig = _make_signature(WEBHOOK_URL, SAMPLE_PAYLOAD, AUTH_TOKEN)
    tampered = {**SAMPLE_PAYLOAD, "Body": "injected content"}
    assert verify_twilio_signature(WEBHOOK_URL, tampered, sig, AUTH_TOKEN) is False


def test_verify_twilio_signature_wrong_url():
    """Sig is tied to the exact URL — a different URL must not validate."""
    sig = _make_signature(WEBHOOK_URL, SAMPLE_PAYLOAD, AUTH_TOKEN)
    assert (
        verify_twilio_signature("https://attacker.example.com/hook", SAMPLE_PAYLOAD, sig, AUTH_TOKEN) is False
    )


def test_verify_twilio_signature_empty_auth_token():
    sig = _make_signature(WEBHOOK_URL, SAMPLE_PAYLOAD, AUTH_TOKEN)
    assert verify_twilio_signature(WEBHOOK_URL, SAMPLE_PAYLOAD, sig, "") is False


def test_verify_twilio_signature_empty_signature():
    assert verify_twilio_signature(WEBHOOK_URL, SAMPLE_PAYLOAD, "", AUTH_TOKEN) is False


def test_verify_twilio_signature_none_credentials():
    assert verify_twilio_signature(WEBHOOK_URL, SAMPLE_PAYLOAD, "sig", None) is False
    assert verify_twilio_signature(WEBHOOK_URL, SAMPLE_PAYLOAD, None, AUTH_TOKEN) is False


def test_verify_twilio_signature_exception_returns_false():
    with patch("twilio.request_validator.RequestValidator") as mock_cls:
        mock_cls.return_value.validate.side_effect = Exception("SDK error")
        assert verify_twilio_signature(WEBHOOK_URL, SAMPLE_PAYLOAD, "sig", AUTH_TOKEN) is False


# ---------------------------------------------------------------------------
# Integration helpers (_headers, _is_meta_131030, _send_meta, _send_twilio)
# ---------------------------------------------------------------------------


def test_headers_accept_asgi_header_tuples():
    headers = _headers(
        {
            "headers": [
                (b"X-Twilio-Signature", b"sig-123"),
                ("X-Hub-Signature-256", "sha256=abc"),
            ]
        }
    )

    assert headers == {
        "x-twilio-signature": "sig-123",
        "x-hub-signature-256": "sha256=abc",
    }


def test_is_meta_131030_handles_int_and_string_codes():
    assert _is_meta_131030({"error": {"code": 131030}}) is True
    assert _is_meta_131030({"error": {"code": "131030"}}) is True
    assert _is_meta_131030({"error": "Unauthorized"}) is False
    assert _is_meta_131030({"error": {"code": 131047}}) is False


class _FakeResponse:
    def __init__(self, status_code: int, *, json_data=None, text: str = "oops"):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self):
        if self._json_data is None:
            raise json.JSONDecodeError("Expecting value", self.text, 0)
        return self._json_data


class _FakeAsyncClient:
    def __init__(self, response: _FakeResponse):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def post(self, *args, **kwargs):
        return self._response


@pytest.mark.asyncio
async def test_send_meta_returns_structured_error_for_non_json_response(monkeypatch):
    monkeypatch.setattr(
        "glc.channels.catalogue.whatsapp.adapter.httpx.AsyncClient",
        lambda: _FakeAsyncClient(_FakeResponse(502)),
    )

    result = await _send_meta(MetaSendPayload(to=OWNER_ID, text=MetaSendText(body="test")))

    assert result == {
        "error": {
            "provider": "meta",
            "code": "non_json_response",
            "message": "non-JSON response",
        },
        "status": 502,
    }


@pytest.mark.asyncio
async def test_send_twilio_returns_structured_error_for_non_json_response(monkeypatch):
    monkeypatch.setattr(
        "glc.channels.catalogue.whatsapp.adapter.httpx.AsyncClient",
        lambda: _FakeAsyncClient(_FakeResponse(503)),
    )

    result = await _send_twilio(TwilioSendPayload(To="whatsapp:+1", From="whatsapp:+2", Body="hi"))

    assert result == {
        "error": {
            "provider": "twilio",
            "code": "non_json_response",
            "message": "non-JSON response",
        },
        "status": 503,
    }


# ---------------------------------------------------------------------------
# US-7: parse_twilio_payload
# ---------------------------------------------------------------------------


def test_parse_twilio_payload_text_message():
    result = parse_twilio_payload(SAMPLE_PAYLOAD, RECEIVED_AT)
    assert result is not None
    assert result.from_id == "14155238886"
    assert result.text == "Hello from Twilio sandbox"
    assert result.message_id == "SM1234567890abcdef1234567890abcdef"
    assert result.profile_name == "Test User"
    assert result.timestamp == RECEIVED_AT


def test_parse_twilio_payload_timestamp_is_received_at():
    """Twilio sends no timestamp field — adapter must use the server receipt time."""
    t1 = datetime(2026, 1, 1, tzinfo=UTC)
    t2 = datetime(2026, 7, 1, tzinfo=UTC)
    r1 = parse_twilio_payload(SAMPLE_PAYLOAD, t1)
    r2 = parse_twilio_payload(SAMPLE_PAYLOAD, t2)
    assert r1.timestamp == t1
    assert r2.timestamp == t2


def test_parse_twilio_payload_media_message_text_is_none():
    """NumMedia != '0' means a media-only message — text must be None, not raise."""
    media_payload = {**SAMPLE_PAYLOAD, "NumMedia": "1", "Body": ""}
    result = parse_twilio_payload(media_payload, RECEIVED_AT)
    assert result is not None
    assert result.text is None
    assert result.from_id == "14155238886"


def test_parse_twilio_payload_missing_waid_returns_none():
    """WaId is required — missing means the payload cannot be identified."""
    payload = {k: v for k, v in SAMPLE_PAYLOAD.items() if k != "WaId"}
    assert parse_twilio_payload(payload, RECEIVED_AT) is None


def test_parse_twilio_payload_no_profile_name():
    """ProfileName is optional — absent must yield profile_name=None, not KeyError."""
    payload = {k: v for k, v in SAMPLE_PAYLOAD.items() if k != "ProfileName"}
    result = parse_twilio_payload(payload, RECEIVED_AT)
    assert result is not None
    assert result.profile_name is None


def test_parse_twilio_payload_waid_is_bare_number():
    """WaId carries a bare E.164 number (no 'whatsapp:' prefix)."""
    result = parse_twilio_payload(SAMPLE_PAYLOAD, RECEIVED_AT)
    assert result is not None
    assert not result.from_id.startswith("whatsapp:")


# ---------------------------------------------------------------------------
# US-8: build_twilio_send_payload
# ---------------------------------------------------------------------------


def test_build_twilio_send_payload_shape():
    """Outbound payload must have To, From, Body with correct values."""
    payload = build_twilio_send_payload(RECIPIENT_PHONE, BOT_PHONE, "Hello back")
    assert payload.Body == "Hello back"
    assert payload.To == f"whatsapp:{RECIPIENT_PHONE}"
    assert payload.From == f"whatsapp:{BOT_PHONE}"


def test_build_twilio_send_payload_adds_whatsapp_prefix_to_both():
    """Bare numbers must be prefixed with 'whatsapp:' before sending."""
    payload = build_twilio_send_payload("14155238886", "+14155551234", "hi")
    assert payload.To.startswith("whatsapp:")
    assert payload.From.startswith("whatsapp:")


def test_build_twilio_send_payload_does_not_double_prefix():
    """Numbers that already carry 'whatsapp:' prefix must not get it twice."""
    payload = build_twilio_send_payload("whatsapp:+14155238886", "whatsapp:+14155551234", "hi")
    assert payload.To.count("whatsapp:") == 1
    assert payload.From.count("whatsapp:") == 1


def test_build_twilio_send_payload_none_text_raises():
    with pytest.raises(ValueError):
        build_twilio_send_payload(RECIPIENT_PHONE, BOT_PHONE, None)


def test_build_twilio_send_payload_empty_text_raises():
    with pytest.raises(ValueError):
        build_twilio_send_payload(RECIPIENT_PHONE, BOT_PHONE, "")


# ---------------------------------------------------------------------------
# Phase 2: on_message + send orchestrators
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_twilio_inbound_populates_cache_and_send_uses_twilio(monkeypatch):
    adapter = Adapter(config={"mock": WhatsappMock()})
    store = get_pairing_store()
    store.force_pair_owner("whatsapp", OWNER_ID, user_handle="owner")

    url = "https://example.com/twilio-webhook"
    auth_token = "test_auth_token"
    monkeypatch.setenv("TWILIO_WEBHOOK_URL", url)
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", auth_token)
    monkeypatch.setenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

    params = {
        "From": "whatsapp:+919999990000",
        "Body": "hello from twilio",
        "WaId": OWNER_ID,
        "ProfileName": "owner",
        "MessageSid": "SM123",
        "NumMedia": "0",
    }
    signature = RequestValidator(auth_token).compute_signature(url, params)
    raw_body = urlencode(params).encode()

    msg = await adapter.on_message({"raw_body": raw_body, "headers": {"X-Twilio-Signature": signature}})
    assert msg is not None
    assert msg.metadata["provider"] == "twilio"
    assert provider_cache[OWNER_ID] == "twilio"

    reply = ChannelReply(channel="whatsapp", channel_user_id=OWNER_ID, text="reply via twilio")
    result = await adapter.send(reply)

    assert result["messages"]
    assert adapter.config["mock"].send_log[-1] == {
        "To": f"whatsapp:{OWNER_ID}",
        "From": "whatsapp:+14155238886",
        "Body": "reply via twilio",
    }


@pytest.mark.asyncio
async def test_twilio_inbound_stranger_is_untrusted(monkeypatch):
    """Twilio inbound from an unknown number → trust_level == 'untrusted'."""
    url = "https://example.com/twilio-webhook"
    auth_token = "test_auth_token"
    monkeypatch.setenv("TWILIO_WEBHOOK_URL", url)
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", auth_token)

    params = {
        "From": "whatsapp:+917777770000",
        "Body": "hi from stranger",
        "WaId": STRANGER_ID,
        "ProfileName": "Stranger",
        "MessageSid": "SMstranger",
        "NumMedia": "0",
    }
    signature = RequestValidator(auth_token).compute_signature(url, params)
    raw_body = urlencode(params).encode()

    adapter = Adapter(config={"mock": WhatsappMock()})
    msg = await adapter.on_message({"raw_body": raw_body, "headers": {"X-Twilio-Signature": signature}})
    # TEMPORARY: stranger passes through in DM mode only because channels.yaml has
    # whatsapp disabled (adapter.py TODO ~line 324). When that TODO is resolved,
    # on_message will return None here — change this to `assert msg is None`.
    assert msg is not None
    assert msg.channel_user_id == STRANGER_ID
    assert msg.trust_level == "untrusted"


@pytest.mark.asyncio
async def test_twilio_tampered_signature_is_rejected(monkeypatch):
    """Tampered X-Twilio-Signature → on_message must return None (HANDOFF §7.11 Phase 2)."""
    url = "https://example.com/twilio-webhook"
    auth_token = "test_auth_token"
    monkeypatch.setenv("TWILIO_WEBHOOK_URL", url)
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", auth_token)

    raw_body = urlencode(SAMPLE_PAYLOAD).encode()
    adapter = Adapter(config={"mock": WhatsappMock()})

    # Wrong signature → rejected
    result = await adapter.on_message(
        {"raw_body": raw_body, "headers": {"X-Twilio-Signature": "tampered_sig"}}
    )
    assert result is None

    # Valid signature → accepted (proves the guard is selective, not always-reject)
    valid_sig = _make_signature(url, SAMPLE_PAYLOAD, auth_token)
    result2 = await adapter.on_message({"raw_body": raw_body, "headers": {"X-Twilio-Signature": valid_sig}})
    assert result2 is not None


@pytest.mark.asyncio
async def test_send_falls_back_to_twilio_on_meta_131030_and_caches_provider(monkeypatch):
    adapter = Adapter(config={})
    store = get_pairing_store()
    store.force_pair_owner("whatsapp", OWNER_ID, user_handle="owner")

    monkeypatch.setenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

    async def fake_send_meta(payload):
        assert payload.to == OWNER_ID
        return {
            "error": {
                "code": 131030,
                "message": "Recipient phone number not in allowed list",
            }
        }

    async def fake_send_twilio(payload):
        assert payload.model_dump() == {
            "To": f"whatsapp:{OWNER_ID}",
            "From": "whatsapp:+14155238886",
            "Body": "fallback",
        }
        return {"sid": "SM456", "status": "queued"}

    monkeypatch.setattr("glc.channels.catalogue.whatsapp.adapter._send_meta", fake_send_meta)
    monkeypatch.setattr("glc.channels.catalogue.whatsapp.adapter._send_twilio", fake_send_twilio)

    reply = ChannelReply(channel="whatsapp", channel_user_id=OWNER_ID, text="fallback")
    result = await adapter.send(reply)

    assert result == {"sid": "SM456", "status": "queued"}
    assert provider_cache[OWNER_ID] == "twilio"


@pytest.mark.asyncio
async def test_mock_send_falls_back_to_twilio_on_meta_131030_and_caches_provider(monkeypatch):
    store = get_pairing_store()
    store.force_pair_owner("whatsapp", OWNER_ID, user_handle="owner")
    monkeypatch.setenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

    mock = WhatsappMock()

    async def fake_send(payload):
        if payload.get("messaging_product") == "whatsapp":
            return {"error": {"code": 131030, "message": "Recipient phone number not in allowed list"}}
        mock.send_log.append(payload)
        return {"sid": "SM789", "status": "queued"}

    mock.send = fake_send
    adapter = Adapter(config={"mock": mock})

    reply = ChannelReply(channel="whatsapp", channel_user_id=OWNER_ID, text="fallback")
    result = await adapter.send(reply)

    assert result == {"sid": "SM789", "status": "queued"}
    assert mock.send_log == [
        {
            "To": f"whatsapp:{OWNER_ID}",
            "From": "whatsapp:+14155238886",
            "Body": "fallback",
        }
    ]
    assert provider_cache[OWNER_ID] == "twilio"


@pytest.mark.asyncio
async def test_mock_send_does_not_cache_provider_on_error():
    store = get_pairing_store()
    store.force_pair_owner("whatsapp", OWNER_ID, user_handle="owner")

    mock = WhatsappMock()

    async def fake_send(payload):
        return {"error": {"code": 80007, "message": "rate limited"}, "status": 429}

    mock.send = fake_send
    adapter = Adapter(config={"mock": mock})

    reply = ChannelReply(channel="whatsapp", channel_user_id=OWNER_ID, text="retry later")
    result = await adapter.send(reply)

    assert result["status"] == 429
    assert OWNER_ID not in provider_cache


@pytest.mark.asyncio
async def test_twilio_send_returns_config_error_when_from_env_missing():
    store = get_pairing_store()
    store.force_pair_owner("whatsapp", OWNER_ID, user_handle="owner")
    provider_cache[OWNER_ID] = "twilio"

    adapter = Adapter(config={"mock": WhatsappMock()})
    reply = ChannelReply(channel="whatsapp", channel_user_id=OWNER_ID, text="reply via twilio")

    result = await adapter.send(reply)

    assert result == {
        "error": {
            "provider": "twilio",
            "code": "missing_twilio_whatsapp_from",
            "message": "TWILIO_WHATSAPP_FROM is not set",
        },
        "status": 500,
    }


@pytest.mark.asyncio
async def test_meta_fallback_returns_config_error_when_twilio_from_env_missing(monkeypatch):
    adapter = Adapter(config={})
    store = get_pairing_store()
    store.force_pair_owner("whatsapp", OWNER_ID, user_handle="owner")

    async def fake_send_meta(payload):
        return {"error": {"code": "131030", "message": "Recipient phone number not in allowed list"}}

    monkeypatch.setattr("glc.channels.catalogue.whatsapp.adapter._send_meta", fake_send_meta)

    reply = ChannelReply(channel="whatsapp", channel_user_id=OWNER_ID, text="fallback")
    result = await adapter.send(reply)

    assert result == {
        "error": {
            "provider": "twilio",
            "code": "missing_twilio_whatsapp_from",
            "message": "TWILIO_WHATSAPP_FROM is not set",
        },
        "status": 500,
    }


@pytest.mark.asyncio
async def test_public_stranger_drop_does_not_populate_provider_cache():
    adapter = Adapter(config={"mock": WhatsappMock(), "is_public_channel": True})
    raw = adapter.config["mock"].queue_stranger_message("hi from public")

    result = await adapter.on_message(raw)

    assert result is None
    assert STRANGER_ID not in provider_cache
