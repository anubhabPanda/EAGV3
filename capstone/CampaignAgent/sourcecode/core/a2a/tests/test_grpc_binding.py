import asyncio

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from sourcecode.core.a2a.grpc_binding import A2AGrpcClient, A2AGrpcServer
from sourcecode.core.a2a.server import A2ADemoServer
from sourcecode.core.a2a.trust import sign_card


def _card():
    return {
        "name": "Local gRPC specialist", "description": "S15 core test agent", "version": "1.0.0",
        "supportedInterfaces": [{"url": "grpc://127.0.0.1:0", "protocolBinding": "GRPC", "protocolVersion": "1.0"}],
        "capabilities": {"streaming": True, "pushNotifications": True},
        "defaultInputModes": ["text/plain"], "defaultOutputModes": ["text/plain"],
        "skills": [{"id": "echo", "name": "Echo", "description": "Returns a result", "tags": ["test"]}],
    }


def _params(text: str):
    return {"message": {"kind": "message", "messageId": "m-1", "role": "user", "parts": [{"kind": "text", "text": text}]}}


@pytest.mark.asyncio
async def test_grpc_send_stream_get_and_cancel():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    core = A2ADemoServer(sign_card(_card(), private_pem, kid="local-1"))
    server = A2AGrpcServer(core)
    client = A2AGrpcClient(await server.start())
    try:
        done = await client.send(_params("answer now"))
        assert done["status"]["state"] == "completed"
        updates = [item async for item in client.stream(_params("stream this"))]
        assert [item["status"]["state"] for item in updates] == ["working", "completed"]
        pending = await client.send(_params("slow work"))
        assert (await client.get(pending["id"]))["status"]["state"] == "working"
        assert (await client.cancel(pending["id"]))["status"]["state"] == "canceled"
        await asyncio.sleep(0.1)
        assert (await client.get(pending["id"]))["status"]["state"] == "canceled"
    finally:
        await client.close()
        await server.stop()
