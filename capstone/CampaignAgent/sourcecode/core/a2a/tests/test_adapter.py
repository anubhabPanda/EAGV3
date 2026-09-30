import asyncio

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from sourcecode.core.a2a.client import A2AClient
from sourcecode.core.a2a.server import A2ADemoServer
from sourcecode.core.a2a.trust import AgentCardTrustPolicy, CardTrustError, sign_card


@pytest.fixture
def keys():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return (
        private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()),
        private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo),
    )


def card():
    return {
        "name": "Local specialist", "description": "S15 core test agent", "version": "1.0.0",
        "supportedInterfaces": [{"url": "http://a2a.test/a2a", "protocolBinding": "JSONRPC", "protocolVersion": "1.0"}],
        "capabilities": {"streaming": True, "pushNotifications": True},
        "defaultInputModes": ["text/plain"], "defaultOutputModes": ["text/plain"],
        "skills": [{"id": "echo", "name": "Echo", "description": "Returns a result", "tags": ["test"]}],
    }


@pytest.fixture
async def setup(keys):
    private, public = keys
    received = []

    async def pushed(event):
        received.append(event)

    server = A2ADemoServer(sign_card(card(), private, kid="local-1"), push_callback=pushed)
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://a2a.test")
    trust = AgentCardTrustPolicy(key_resolver=lambda kid: public if kid == "local-1" else None)
    yield server, A2AClient(http, trust), received
    await http.aclose()


@pytest.mark.asyncio
async def test_discovery_sync_and_stream(setup):
    _, client, _ = setup
    agent = await client.discover("http://a2a.test")
    done = await client.send(agent, "answer now")
    assert done["status"]["state"] == "completed"
    updates = [update async for update in client.stream(agent, "stream this")]
    assert [item["status"]["state"] for item in updates] == ["working", "completed"]


@pytest.mark.asyncio
async def test_async_push_and_cancellation(setup):
    server, client, received = setup
    agent = await client.discover("http://a2a.test")
    pending = await client.send(agent, "async report", push_url="http://graph.test/callback")
    task_id = pending["id"]
    await asyncio.sleep(0.12)
    assert (await client.get(agent, task_id))["status"]["state"] == "completed"
    assert received[-1]["params"]["id"] == task_id
    slow = await client.send(agent, "slow work")
    cancelled = await client.cancel(agent, slow["id"])
    assert cancelled["status"]["state"] == "canceled"
    await asyncio.sleep(0.1)
    assert server.tasks[slow["id"]].state.value == "canceled"


@pytest.mark.asyncio
async def test_tampered_card_is_rejected(setup):
    server, client, _ = setup
    server.card["name"] = "tampered after signing"
    with pytest.raises(CardTrustError):
        await client.discover("http://a2a.test")
