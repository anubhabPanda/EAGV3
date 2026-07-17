"""V9 compatibility shim — assert that the routes S9 and S10 client
code call against the V9 gateway exist with the same shape on glc_v1.

These tests do not exercise the upstream LLM calls (no live keys in
CI); they verify the route surface, OpenAPI schema, request validation,
and the listings endpoints return the expected V9 keys.
"""

from __future__ import annotations


def test_v9_routes_are_registered(app_client):
    openapi = app_client.get("/openapi.json").json()
    paths = set(openapi["paths"].keys())
    for p in [
        "/v1/chat",
        "/v1/chat/batch",
        "/v1/vision",
        "/v1/embed",
        "/v1/cost/by_agent",
        "/v1/providers",
        "/v1/capabilities",
        "/v1/status",
        "/v1/routers",
        "/v1/calls",
        "/v1/embedders",
    ]:
        assert p in paths, f"missing V9 route {p}"


def test_new_s11_routes_are_registered(app_client):
    openapi = app_client.get("/openapi.json").json()
    paths = set(openapi["paths"].keys())
    for p in [
        "/v1/transcribe",
        "/v1/speak",
        "/v1/control/kill",
        "/v1/control/pair",
        "/v1/control/pair/confirm",
        "/v1/control/presence",
    ]:
        assert p in paths


def test_v1_providers_shape_unchanged(app_client):
    body = app_client.get("/v1/providers").json()
    # V9 shape: order, providers, shortcuts, limits, models
    for k in ("order", "providers", "shortcuts", "limits", "models"):
        assert k in body


def test_v1_status_shape_unchanged(app_client):
    body = app_client.get("/v1/status").json()
    for k in ("order", "live", "today", "limits"):
        assert k in body


def test_v1_capabilities_returns_per_provider_caps(app_client):
    body = app_client.get("/v1/capabilities").json()
    # Even with zero providers wired, the shape must be a dict.
    assert isinstance(body, dict)


def test_v1_cost_by_agent_returns_dict(app_client):
    body = app_client.get("/v1/cost/by_agent").json()
    assert isinstance(body, dict)


def test_chat_request_rejects_bad_provider(app_client):
    r = app_client.post("/v1/chat", json={"prompt": "hi", "provider": "no_such_provider"})
    # If no providers wired at all, the validation hits 400; if they are
    # wired, the candidate list is empty (also 400).
    assert r.status_code in (400, 503)


def test_chat_request_minimal_body_validates(app_client):
    """The request body schema accepts a bare prompt with no provider."""
    # We don't care about the upstream call result — just that Pydantic
    # accepts the body shape (i.e., not a 422).
    r = app_client.post("/v1/chat", json={"prompt": "hi"})
    assert r.status_code != 422


def test_embed_request_413_on_oversize(app_client):
    huge = "x" * 9000
    r = app_client.post("/v1/embed", json={"text": huge})
    # 413 if embedders exist; 503 if none configured at all.
    assert r.status_code in (413, 503)


def test_healthz(app_client):
    r = app_client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["ok"] is True
