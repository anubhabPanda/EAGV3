"""Mock-API fake for Signal via signal-cli's JSON-RPC service.

Wire-format source:
  https://github.com/AsamK/signal-cli/wiki/JSON-RPC-service
  https://github.com/AsamK/signal-cli/blob/master/man/signal-cli-jsonrpc.5.adoc

Inbound: a JSON-RPC notification (no `id` field), method `receive`,
`params.envelope.source` is the sender phone number, the message body
sits under `params.envelope.dataMessage.message`. Group messages also
include `params.envelope.dataMessage.groupInfo.groupId`.

Outbound: a JSON-RPC request `{jsonrpc, id, method: "send",
params: {recipient | groupId, message}}`.

Helpers
-------
queue_owner_message(text)              → DM notification from owner
queue_stranger_message(text)           → DM notification from stranger
queue_group_message(text, group_id)    → group notification with groupId
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

OWNER_PHONE = "+19999999999"  # E.164 with leading +.
STRANGER_PHONE = "+17777777777"
OWNER_ID = OWNER_PHONE
STRANGER_ID = STRANGER_PHONE

GROUP_ID_B64 = "groupAbCdEf=="


def _notification(
    *, source: str, source_name: str, body: str, group_id: str | None = None, timestamp: int = 1700000000000
) -> dict[str, Any]:
    data_message: dict[str, Any] = {
        "timestamp": timestamp,
        "message": body,
        "expiresInSeconds": 0,
        "viewOnce": False,
    }
    if group_id:
        data_message["groupInfo"] = {"groupId": group_id, "type": "DELIVER"}
    return {
        "jsonrpc": "2.0",
        "method": "receive",
        "params": {
            "envelope": {
                "source": source,
                "sourceNumber": source,
                "sourceUuid": "uuid-" + source[1:],
                "sourceName": source_name,
                "sourceDevice": 1,
                "timestamp": timestamp,
                "dataMessage": data_message,
            },
            "account": "+15555550100",
        },
    }


@dataclass
class SignalMock:
    inbound_events: list[dict[str, Any]] = field(default_factory=list)
    send_log: list[dict[str, Any]] = field(default_factory=list)
    rate_limited: bool = False
    _disconnect_pending: bool = False
    _next_rpc: int = 100

    def _rpc_id(self) -> int:
        self._next_rpc += 1
        return self._next_rpc

    def queue_owner_message(self, text: str = "hello") -> dict[str, Any]:
        ev = _notification(source=OWNER_PHONE, source_name="owner", body=text)
        self.inbound_events.append(ev)
        return ev

    def queue_stranger_message(self, text: str = "ping") -> dict[str, Any]:
        ev = _notification(source=STRANGER_PHONE, source_name="stranger", body=text)
        self.inbound_events.append(ev)
        return ev

    def queue_group_message(
        self, text: str = "hi all", group_id: str = GROUP_ID_B64, from_owner: bool = True
    ) -> dict[str, Any]:
        sender = (OWNER_PHONE, "owner") if from_owner else (STRANGER_PHONE, "stranger")
        ev = _notification(source=sender[0], source_name=sender[1], body=text, group_id=group_id)
        self.inbound_events.append(ev)
        return ev

    async def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.rate_limited:
            return {
                "jsonrpc": "2.0",
                "id": payload.get("id"),
                "error": {"code": -32603, "message": "rate limited"},
                "status": 429,
            }
        self.send_log.append(payload)
        return {"jsonrpc": "2.0", "id": payload.get("id"), "result": {"timestamp": 1700000000999}}

    def force_disconnect(self) -> None:
        self._disconnect_pending = True

    def pop_disconnect(self) -> bool:
        was = self._disconnect_pending
        self._disconnect_pending = False
        return was
