"""The control plane fails closed, on every write path, without exception.

A subscription carries `allowed_side_effects` and a budget: it is the object the
whole session's security argument rests on. An unauthenticated write there hands
an anonymous caller the authority to decide what the agent may do and how much it
may spend. Starting a run and resuming a parked node both spend money too.

The shape being guarded against is `if expected and not compare_digest(...)`,
which reads like a check and behaves like an open door whenever the variable is
unset — which is exactly the state a fresh checkout is in.
"""
from __future__ import annotations

import conftest
import pytest

WRITE_PATHS = [
    ("put", "/v1/agent/subscriptions/probe", {"id": "probe", "instruction": "watch", "tenant_id": "t"}),
    ("post", "/v1/agent/events", {"id": "e1", "source": "s", "type": "t",
                                  "occurred_at": "2026-08-05T09:00:00Z"}),
    ("post", "/v1/agent/runs", {"prompt": "hello", "tenant_id": "t"}),
    ("post", "/v1/agent/runs/run-1/resume", {}),
]


@pytest.mark.parametrize(("method", "path", "body"), WRITE_PATHS)
def test_a_write_path_refuses_to_serve_when_no_token_is_configured(
    app_client, monkeypatch, method, path, body
) -> None:
    monkeypatch.delenv("S17_CONTROL_TOKEN", raising=False)
    response = getattr(app_client, method)(path, json=body)
    assert response.status_code == 503
    assert "S17_CONTROL_TOKEN" in response.json()["detail"]


@pytest.mark.parametrize(("method", "path", "body"), WRITE_PATHS)
def test_a_write_path_rejects_the_wrong_token(app_client, method, path, body) -> None:
    response = getattr(app_client, method)(path, json=body,
                                           headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401


def test_the_right_token_is_accepted(app_client) -> None:
    response = app_client.put("/v1/agent/subscriptions/probe",
                              json={"id": "probe", "instruction": "watch", "tenant_id": "t"})
    assert response.status_code == 200
    assert response.json()["accepted"] is True


def test_the_completion_callback_has_its_own_token_and_also_fails_closed(
    app_client, monkeypatch
) -> None:
    """A remote job service may finish work; it may not write subscriptions."""
    body = {"handle": "job-1", "event_type": "job.completed", "success": True, "payload": {}}

    # The control token is not the completion token.
    denied = app_client.post("/v1/agent/completions", json=body)
    assert denied.status_code == 401

    accepted = app_client.post("/v1/agent/completions", json=body,
                               headers={"Authorization": f"Bearer {conftest.COMPLETION_TOKEN}"})
    # Unknown handle, but authenticated: the gate passed and the store answered.
    assert accepted.status_code == 200
    assert accepted.json()["duplicate_or_unknown"] is True

    monkeypatch.delenv("S17_COMPLETION_TOKEN", raising=False)
    unset = app_client.post("/v1/agent/completions", json=body,
                            headers={"Authorization": f"Bearer {conftest.COMPLETION_TOKEN}"})
    assert unset.status_code == 503


def test_read_only_observability_is_available_to_an_operator(app_client) -> None:
    """Liveness answers 503 when the watcher is silent, which is the alarm."""
    liveness = app_client.get("/v1/agent/liveness")
    assert liveness.status_code == 503
    assert liveness.json()["alive"] is False

    report = app_client.get("/v1/agent/report")
    assert report.status_code == 200
    assert report.json()["totals"]["events_seen"] == 0

    markdown = app_client.get("/v1/agent/report", params={"fmt": "markdown"})
    assert "Overnight report" in markdown.text
    assert "NOT ALIVE" in markdown.text


def test_the_operator_console_is_served_and_is_read_only(app_client) -> None:
    """§9 promises an operations page. It has to exist, and it has to be inert.

    The console reads the durable history and nothing else. A page that could
    create a subscription would be the exact hole the control plane exists to
    close, so it ships with no write path at all.
    """
    page = app_client.get("/console")
    assert page.status_code == 200
    body = page.text
    assert "autonomy console" in body.lower()

    # It reads the endpoints an operator needs...
    for endpoint in ("/v1/agent/liveness", "/v1/agent/refusals",
                     "/v1/agent/report", "/v1/agent/events/stream?after="):
        assert endpoint in body, f"console never calls {endpoint}"

    # ...and never writes. No method:POST/PUT/DELETE anywhere in the page.
    lowered = body.lower()
    for verb in ('method: "post"', "method:'post'", 'method: "put"',
                 'method: "delete"', "_method: post"):
        assert verb not in lowered, f"console contains a write call: {verb}"
