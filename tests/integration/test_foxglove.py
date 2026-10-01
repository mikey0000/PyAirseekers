from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import aiohttp
import pytest

from pyairseekers import AirseekersTransportError, FoxgloveClient

if TYPE_CHECKING:
    from tests.integration.fakeserver.foxglove import FakeBridge


class TestFoxgloveClient:
    async def test_decodes_subscribed_messages_and_reports_disconnect(
        self, fake_bridge: tuple[FakeBridge, str, int]
    ) -> None:
        bridge, host, port = fake_bridge
        received: asyncio.Queue[tuple[str, str, object]] = asyncio.Queue()
        disconnected = asyncio.Event()

        async def on_message(topic: str, schema: str, msg: object) -> None:
            await received.put((topic, schema, msg))

        async def on_connection(connected: bool) -> None:
            if not connected:
                disconnected.set()

        async with aiohttp.ClientSession() as session:
            client = FoxgloveClient(host, port, session)
            info = await client.connect()
            await client.subscribe(["/task_info", "/not_advertised"], on_message, on_connection)
            await asyncio.wait_for(bridge.subscribed.wait(), timeout=5)
            await bridge.outbox.put('{"state": "running"}')
            topic, schema, msg = await asyncio.wait_for(received.get(), timeout=5)
            await bridge.outbox.put(None)
            await asyncio.wait_for(disconnected.wait(), timeout=5)
            await client.disconnect()

        assert info.session_id == "s1"
        assert (topic, schema) == ("/task_info", "std_msgs/String")
        assert getattr(msg, "data", None) == '{"state": "running"}'

    async def test_unreachable_bridge_is_a_transport_error(self) -> None:
        async with aiohttp.ClientSession() as session:
            client = FoxgloveClient("127.0.0.1", 9, session)
            with pytest.raises(AirseekersTransportError):
                await client.connect()
