"""gRPC transport for the S15 core A2A task adapter.

It uses a real ``grpc.aio`` server/channel and Protocol Buffers wire encoding.
The methods deliberately mirror the A2A v1 ``lf.a2a.v1.A2AService`` core task
operations, while ``google.protobuf.Struct`` keeps this local harness small.
Replacing the generated contract with the official full a2a.proto is therefore
an additive interoperability upgrade, not a graph/runtime redesign.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import grpc
from google.protobuf.json_format import MessageToDict, ParseDict
from google.protobuf.struct_pb2 import Struct

from .server import A2ADemoServer

SERVICE = "lf.a2a.v1.A2AService"


def _wire(message: Struct) -> dict[str, Any]:
    return MessageToDict(message, preserving_proto_field_name=False)


def _struct(value: dict[str, Any]) -> Struct:
    message = Struct()
    ParseDict(value, message)
    return message


class _A2AService:
    def __init__(self, core: A2ADemoServer) -> None:
        self.core = core

    async def SendMessage(self, request: Struct, context) -> Struct:
        return _struct(await self.core.send(_wire(request)))

    async def SendStreamingMessage(self, request: Struct, context) -> AsyncIterator[Struct]:
        async for update in self.core.stream_updates(_wire(request)):
            yield _struct(update)

    async def GetTask(self, request: Struct, context) -> Struct:
        try:
            return _struct(self.core.get(str(_wire(request).get("id", ""))))
        except ValueError as error:
            await context.abort(grpc.StatusCode.NOT_FOUND, str(error))

    async def CancelTask(self, request: Struct, context) -> Struct:
        try:
            return _struct(await self.core.cancel(str(_wire(request).get("id", ""))))
        except ValueError as error:
            await context.abort(grpc.StatusCode.NOT_FOUND, str(error))


class A2AGrpcServer:
    """Owns a local gRPC A2A binding around the same task core as JSON-RPC."""

    def __init__(self, core: A2ADemoServer) -> None:
        self.core = core
        self.server = grpc.aio.server()
        service = _A2AService(core)
        self.server.add_generic_rpc_handlers((grpc.method_handlers_generic_handler(SERVICE, {
            "SendMessage": grpc.unary_unary_rpc_method_handler(
                service.SendMessage, request_deserializer=Struct.FromString, response_serializer=Struct.SerializeToString),
            "SendStreamingMessage": grpc.unary_stream_rpc_method_handler(
                service.SendStreamingMessage, request_deserializer=Struct.FromString, response_serializer=Struct.SerializeToString),
            "GetTask": grpc.unary_unary_rpc_method_handler(
                service.GetTask, request_deserializer=Struct.FromString, response_serializer=Struct.SerializeToString),
            "CancelTask": grpc.unary_unary_rpc_method_handler(
                service.CancelTask, request_deserializer=Struct.FromString, response_serializer=Struct.SerializeToString),
        }),))
        self.port: int | None = None

    async def start(self) -> str:
        self.port = self.server.add_insecure_port("127.0.0.1:0")
        if not self.port:
            raise RuntimeError("could not allocate local gRPC port")
        await self.server.start()
        return f"127.0.0.1:{self.port}"

    async def stop(self) -> None:
        await self.server.stop(grace=0)


class A2AGrpcClient:
    """A live-graph-ready client for the gRPC A2A binding."""

    def __init__(self, target: str) -> None:
        self.channel = grpc.aio.insecure_channel(target)
        codec = {"request_serializer": Struct.SerializeToString, "response_deserializer": Struct.FromString}
        self.send_rpc = self.channel.unary_unary(f"/{SERVICE}/SendMessage", **codec)
        self.stream_rpc = self.channel.unary_stream(f"/{SERVICE}/SendStreamingMessage", **codec)
        self.get_rpc = self.channel.unary_unary(f"/{SERVICE}/GetTask", **codec)
        self.cancel_rpc = self.channel.unary_unary(f"/{SERVICE}/CancelTask", **codec)

    async def close(self) -> None:
        await self.channel.close()

    async def send(self, params: dict[str, Any]) -> dict[str, Any]:
        return _wire(await self.send_rpc(_struct(params)))

    async def stream(self, params: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        call = self.stream_rpc(_struct(params))
        async for item in call:
            yield _wire(item)

    async def get(self, task_id: str) -> dict[str, Any]:
        return _wire(await self.get_rpc(_struct({"id": task_id})))

    async def cancel(self, task_id: str) -> dict[str, Any]:
        return _wire(await self.cancel_rpc(_struct({"id": task_id})))
