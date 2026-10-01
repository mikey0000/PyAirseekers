"""aiohttp fake of ros-foxglove-bridge speaking foxglove.websocket.v1."""

from __future__ import annotations

import asyncio
import base64
import struct

from aiohttp import web

SUBPROTOCOL = "foxglove.websocket.v1"
STRING_CHANNEL = {"id": 7, "topic": "/task_info", "encoding": "ros1", "schemaName": "std_msgs/String"}
STRING_SCHEMA = "string data\n"


def ros1_string(value: str) -> bytes:
    """Serialise a std_msgs/String the way ROS1 does."""
    raw = value.encode()
    return struct.pack("<I", len(raw)) + raw


class FakeBridge:
    """Advertises one std_msgs/String channel and publishes queued values."""

    def __init__(self) -> None:
        self.app = web.Application()
        self.app.router.add_get("/", self._ws)
        self.outbox: asyncio.Queue[str | None] = asyncio.Queue()
        self.subscribed = asyncio.Event()

    async def _ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(protocols=[SUBPROTOCOL])
        await ws.prepare(request)
        await ws.send_json({"op": "serverInfo", "name": "fake", "capabilities": [], "sessionId": "s1"})
        schema = base64.b64encode(STRING_SCHEMA.encode()).decode()
        await ws.send_json({"op": "advertise", "channels": [{**STRING_CHANNEL, "schema": schema}]})
        msg = await ws.receive_json()
        sub_id = msg["subscriptions"][0]["id"]
        self.subscribed.set()
        while (value := await self.outbox.get()) is not None:
            await ws.send_bytes(b"\x01" + struct.pack("<IQ", sub_id, 0) + ros1_string(value))
        await ws.close()
        return ws
