"""aiohttp fake of ros-foxglove-bridge speaking foxglove.websocket.v1."""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
import struct

from aiohttp import WSMsgType, web

SUBPROTOCOL = "foxglove.websocket.v1"
STRING_CHANNEL = {"id": 7, "topic": "/task_info", "encoding": "ros1", "schemaName": "std_msgs/String"}
STRING_SCHEMA = "string data\n"
CTRL_SERVICE_ID = 92
TRIGGER_REQUEST = "string arg  # stop / pause / resume\n"
TRIGGER_RESPONSE = "int32 result\nstring message\n"


def ros1_string(value: str) -> bytes:
    """Serialise a std_msgs/String the way ROS1 does."""
    raw = value.encode()
    return struct.pack("<I", len(raw)) + raw


@dataclass
class BridgeState:
    """Server-side state and fault knobs."""

    capabilities: list[str] = field(default_factory=lambda: ["services"])
    service_name: str = "/controller/ctrl"
    nested_schemas: bool = False
    trigger_request_schema: str = TRIGGER_REQUEST
    trigger_response_schema: str = TRIGGER_RESPONSE
    trigger_result: int = 0
    trigger_message: str = "ok"
    raw_response: bytes | None = None
    fail_calls: bool = False
    answer_calls: bool = True
    calls: list[str] = field(default_factory=list)


class FakeBridge:
    """Advertises one std_msgs/String channel and ``/controller/ctrl``.

    Publishes values put on ``outbox`` (``None`` closes the socket) and
    answers service calls according to ``state``.
    """

    def __init__(self) -> None:
        self.app = web.Application()
        self.app.router.add_get("/", self._ws)
        self.state = BridgeState()
        # str: publish on /task_info; dict: send as JSON; None: close the socket
        self.outbox: asyncio.Queue[str | dict[str, object] | None] = asyncio.Queue()
        self.subscribed = asyncio.Event()
        self.call_received = asyncio.Event()
        self._sub_id: int | None = None

    async def _ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(protocols=[SUBPROTOCOL])
        await ws.prepare(request)
        await ws.send_json(
            {"op": "serverInfo", "name": "fake", "capabilities": self.state.capabilities, "sessionId": "s1"}
        )
        schema = base64.b64encode(STRING_SCHEMA.encode()).decode()
        await ws.send_json({"op": "advertise", "channels": [{**STRING_CHANNEL, "schema": schema}]})
        await ws.send_json({"op": "advertiseServices", "services": [self._service()]})
        reader = asyncio.create_task(self._read(ws))
        while (item := await self.outbox.get()) is not None:
            if isinstance(item, dict):
                await ws.send_json(item)
            elif self._sub_id is not None:
                await ws.send_bytes(b"\x01" + struct.pack("<IQ", self._sub_id, 0) + ros1_string(item))
        reader.cancel()
        await ws.close()
        return ws

    def _service(self) -> dict[str, object]:
        service: dict[str, object] = {
            "id": CTRL_SERVICE_ID,
            "name": self.state.service_name,
            "type": "mower_msgs/Trigger",
        }
        if self.state.nested_schemas:
            service["request"] = {"encoding": "ros1", "schema": self.state.trigger_request_schema}
            service["response"] = {"encoding": "ros1", "schema": self.state.trigger_response_schema}
        else:
            service["requestSchema"] = self.state.trigger_request_schema
            service["responseSchema"] = self.state.trigger_response_schema
        return service

    async def _read(self, ws: web.WebSocketResponse) -> None:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT and (data := msg.json()).get("op") == "subscribe":
                self._sub_id = data["subscriptions"][0]["id"]
                self.subscribed.set()
            elif msg.type == WSMsgType.BINARY and msg.data[0] == 0x02:
                await self._answer_call(ws, msg.data)

    async def _answer_call(self, ws: web.WebSocketResponse, frame: bytes) -> None:
        service_id, call_id, enc_len = struct.unpack_from("<III", frame, 1)
        payload = frame[13 + enc_len :]
        (arg_len,) = struct.unpack_from("<I", payload, 0)
        self.state.calls.append(payload[4 : 4 + arg_len].decode())
        self.call_received.set()
        if not self.state.answer_calls:
            return
        if self.state.fail_calls:
            await ws.send_json(
                {"op": "serviceCallFailure", "serviceId": service_id, "callId": call_id, "message": "node down"}
            )
            return
        encoding = b"ros1"
        response = self.state.raw_response
        if response is None:
            response = struct.pack("<i", self.state.trigger_result) + ros1_string(self.state.trigger_message)
        await ws.send_bytes(struct.pack("<BIII", 0x03, service_id, call_id, len(encoding)) + encoding + response)
