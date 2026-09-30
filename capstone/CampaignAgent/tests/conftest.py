from __future__ import annotations

import pytest

CONTROL_TOKEN = "test-control-token"
COMPLETION_TOKEN = "test-completion-token"


@pytest.fixture(autouse=True)
def _isolated_state(monkeypatch, tmp_path):
    monkeypatch.setenv("S17_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("S17_A2A_GRPC_ENABLED", "0")
    monkeypatch.setenv("S17_SANDBOX_ROOT", str(tmp_path / "sandbox"))
    # The control plane fails closed. Tests configure a token exactly as a real
    # deployment must; they do not get a bypass, so the gates stay exercised
    # rather than disabled for convenience.
    monkeypatch.setenv("S17_CONTROL_TOKEN", CONTROL_TOKEN)
    monkeypatch.setenv("S17_COMPLETION_TOKEN", COMPLETION_TOKEN)
    (tmp_path / "sandbox").mkdir()


@pytest.fixture
def app_client():
    from fastapi.testclient import TestClient

    from sourcecode.main import app

    with TestClient(app, headers={"Authorization": f"Bearer {CONTROL_TOKEN}"}) as client:
        yield client
