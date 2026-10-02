from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer
import pytest

from pyairseekers import AirseekersTransportError, FoxgloveClient
from pyairseekers.local import foxglove

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


class TestConnectionLifecycle:
    @pytest.mark.regression
    async def test_a_malformed_frame_does_not_end_the_stream(self, fake_bridge: tuple[FakeBridge, str, int]) -> None:
        """One bad frame used to end the receive loop and silently stop all telemetry."""
        bridge, host, port = fake_bridge
        received: asyncio.Queue[object] = asyncio.Queue()

        async def on_message(topic: str, schema: str, msg: object) -> None:
            await received.put(msg)

        async with aiohttp.ClientSession() as session:
            client = FoxgloveClient(host, port, session)
            await client.connect()
            await client.subscribe(["/task_info"], on_message)
            await asyncio.wait_for(bridge.subscribed.wait(), timeout=5)
            await bridge.outbox.put({"op": "advertise", "channels": [{"no": "id"}]})
            await bridge.outbox.put("still alive")
            msg = await asyncio.wait_for(received.get(), timeout=5)
            connected = client.connected
            await client.disconnect()

        assert getattr(msg, "data", None) == "still alive"
        assert connected

    async def test_a_dropped_connection_reports_not_connected(self, fake_bridge: tuple[FakeBridge, str, int]) -> None:
        bridge, host, port = fake_bridge
        lost = asyncio.Event()

        async def on_connection(connected: bool) -> None:
            if not connected:
                lost.set()

        async def on_message(topic: str, schema: str, msg: object) -> None:
            return

        async with aiohttp.ClientSession() as session:
            client = FoxgloveClient(host, port, session)
            await client.connect()
            await client.subscribe(["/task_info"], on_message, on_connection)
            await bridge.outbox.put(None)
            await asyncio.wait_for(lost.wait(), timeout=5)

            assert not client.connected
            await client.disconnect()

    async def test_explicit_disconnect_does_not_report_a_loss(self, fake_bridge: tuple[FakeBridge, str, int]) -> None:
        _, host, port = fake_bridge
        reports: list[bool] = []

        async def on_connection(connected: bool) -> None:
            reports.append(connected)

        async def on_message(topic: str, schema: str, msg: object) -> None:
            return

        async with aiohttp.ClientSession() as session:
            client = FoxgloveClient(host, port, session)
            await client.connect()
            await client.subscribe(["/task_info"], on_message, on_connection)
            await client.disconnect()

        assert reports == []

    @pytest.mark.regression
    async def test_reconnecting_replaces_the_old_connection(self, fake_bridge: tuple[FakeBridge, str, int]) -> None:
        """A second connect left the first receive loop running alongside the new one."""
        _, host, port = fake_bridge
        async with aiohttp.ClientSession() as session:
            client = FoxgloveClient(host, port, session)
            await client.connect()
            first = client._receive_task
            await client.connect()

            assert first is not None
            assert first.done()
            assert client.connected
            assert "/task_info" in client.available_topics
            await client.disconnect()


@pytest.mark.regression
async def test_connect_timeout_names_the_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A timeout's str() is empty, so the error read "Foxglove bridge at ws://...: " with no reason."""
    silent = asyncio.Event()

    async def never_says_hello(request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(protocols=["foxglove.websocket.v1"])
        await ws.prepare(request)
        await silent.wait()
        return ws

    app = web.Application()
    app.router.add_get("/", never_says_hello)
    server = TestServer(app)
    await server.start_server()
    monkeypatch.setattr(foxglove, "CONNECT_TIMEOUT", 0.05)
    try:
        async with aiohttp.ClientSession() as session:
            client = FoxgloveClient(str(server.host), int(server.port or 0), session)
            with pytest.raises(AirseekersTransportError, match="TimeoutError"):
                await client.connect()
            await client.disconnect()
    finally:
        silent.set()
        await server.close()


@pytest.mark.regression
async def test_closed_host_session_is_a_transport_error(fake_bridge: tuple[FakeBridge, str, int]) -> None:
    """Connecting with a host's closed session raised aiohttp's bare RuntimeError."""
    _, host, port = fake_bridge
    session = aiohttp.ClientSession()
    await session.close()
    client = FoxgloveClient(host, port, session)

    with pytest.raises(AirseekersTransportError, match="session is closed"):
        await client.connect()
