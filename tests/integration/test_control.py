from __future__ import annotations

import asyncio
import struct
from typing import TYPE_CHECKING

import aiohttp
import pytest

from pyairseekers import AirseekersServiceError, AirseekersTransportError, FoxgloveClient, MowerController
from pyairseekers.local import foxglove
from tests.integration.fakeserver.foxglove import CTRL_SERVICE_ID

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from tests.integration.fakeserver.foxglove import FakeBridge

type Bridge = tuple[FakeBridge, str, int]


@pytest.fixture
async def client(fake_bridge: Bridge) -> AsyncIterator[FoxgloveClient]:
    _, host, port = fake_bridge
    async with aiohttp.ClientSession() as session:
        client = FoxgloveClient(host, port, session)
        yield client
        await client.disconnect()


async def connected(client: FoxgloveClient) -> MowerController:
    await client.connect()
    return MowerController(client)


class TestCommands:
    @pytest.mark.parametrize("command", ["stop", "pause"])
    async def test_sends_the_verified_argument_and_returns_the_answer(
        self, client: FoxgloveClient, fake_bridge: Bridge, command: str
    ) -> None:
        bridge, _, _ = fake_bridge
        controller = await connected(client)

        result = await getattr(controller, command)()

        assert bridge.state.calls == [command]
        assert (result.result, result.message) == (0, "ok")

    def test_resume_is_not_offered_until_verified(self) -> None:
        assert not hasattr(MowerController, "resume")

    async def test_nested_schema_advertisement_is_understood(self, client: FoxgloveClient, fake_bridge: Bridge) -> None:
        bridge, _, _ = fake_bridge
        bridge.state.nested_schemas = True
        controller = await connected(client)

        assert (await controller.stop()).result == 0


class TestRejections:
    async def test_non_zero_result_raises_with_code_message_and_service(
        self, client: FoxgloveClient, fake_bridge: Bridge
    ) -> None:
        bridge, _, _ = fake_bridge
        bridge.state.trigger_result = 1
        bridge.state.trigger_message = "not running"
        controller = await connected(client)

        with pytest.raises(AirseekersServiceError, match="not running") as err:
            await controller.stop()

        assert (err.value.code, err.value.path) == (1, "/controller/ctrl")

    async def test_service_call_failure_raises_naming_the_service(
        self, client: FoxgloveClient, fake_bridge: Bridge
    ) -> None:
        bridge, _, _ = fake_bridge
        bridge.state.fail_calls = True
        controller = await connected(client)

        with pytest.raises(AirseekersServiceError, match="node down") as err:
            await controller.pause()

        assert err.value.path == "/controller/ctrl"

    @pytest.mark.parametrize(
        ("raw", "reason"),
        [
            (b"\x00\x00", "truncated"),
            (struct.pack("<iI", 0, 10) + b"short", "truncated"),
            (struct.pack("<iI", 0, 2) + b"\xff\xfe", "not UTF-8"),
        ],
    )
    async def test_malformed_response_raises(
        self, client: FoxgloveClient, fake_bridge: Bridge, raw: bytes, reason: str
    ) -> None:
        bridge, _, _ = fake_bridge
        bridge.state.raw_response = raw
        controller = await connected(client)

        with pytest.raises(AirseekersServiceError, match=reason):
            await controller.stop()


class TestSafetyGuards:
    @pytest.mark.parametrize(
        ("knob", "schema"),
        [("trigger_request_schema", "int32 code\n"), ("trigger_response_schema", "bool success\n")],
    )
    async def test_changed_schema_is_refused_before_anything_is_sent(
        self, client: FoxgloveClient, fake_bridge: Bridge, knob: str, schema: str
    ) -> None:
        bridge, _, _ = fake_bridge
        setattr(bridge.state, knob, schema)
        controller = await connected(client)

        with pytest.raises(AirseekersServiceError, match="verified Trigger schema"):
            await controller.stop()

        assert client._next_call_id == 1

    async def test_bridge_without_services_capability_is_refused(
        self, client: FoxgloveClient, fake_bridge: Bridge
    ) -> None:
        bridge, _, _ = fake_bridge
        bridge.state.capabilities = []
        controller = await connected(client)

        with pytest.raises(AirseekersServiceError, match="does not offer"):
            await controller.stop()

        assert client._next_call_id == 1

    async def test_service_not_advertised_is_refused(self, client: FoxgloveClient, fake_bridge: Bridge) -> None:
        bridge, _, _ = fake_bridge
        bridge.state.service_name = "/controller/other"
        controller = await connected(client)

        with pytest.raises(AirseekersServiceError, match="not advertised"):
            await controller.stop()

    async def test_withdrawn_service_is_refused(self, client: FoxgloveClient, fake_bridge: Bridge) -> None:
        bridge, _, _ = fake_bridge
        controller = await connected(client)
        marker = asyncio.Event()

        async def on_message(topic: str, schema: str, msg: object) -> None:
            marker.set()

        await client.subscribe(["/task_info"], on_message)
        await asyncio.wait_for(bridge.subscribed.wait(), timeout=5)
        # Frames arrive in order: once the marker message lands, the withdrawal has too
        await bridge.outbox.put({"op": "unadvertiseServices", "serviceIds": [CTRL_SERVICE_ID]})
        await bridge.outbox.put("marker")
        await asyncio.wait_for(marker.wait(), timeout=5)

        assert "/controller/ctrl" not in client.available_services
        with pytest.raises(AirseekersServiceError, match="not advertised"):
            await controller.stop()


class TestLiveness:
    async def test_no_answer_is_a_transport_error(
        self, client: FoxgloveClient, fake_bridge: Bridge, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bridge, _, _ = fake_bridge
        bridge.state.answer_calls = False
        monkeypatch.setattr(foxglove, "SERVICE_CALL_TIMEOUT", 0.05)
        controller = await connected(client)

        with pytest.raises(AirseekersTransportError, match="no response"):
            await controller.stop()

    async def test_connection_drop_fails_the_call_in_flight(self, client: FoxgloveClient, fake_bridge: Bridge) -> None:
        bridge, _, _ = fake_bridge
        bridge.state.answer_calls = False
        controller = await connected(client)

        call = asyncio.create_task(controller.stop())
        await asyncio.wait_for(bridge.call_received.wait(), timeout=5)
        await bridge.outbox.put(None)

        with pytest.raises(AirseekersTransportError, match="connection closed"):
            await asyncio.wait_for(call, timeout=5)

    @pytest.mark.regression
    async def test_calls_fail_fast_after_disconnect(self, client: FoxgloveClient) -> None:
        """After disconnect, a call waited the full connect timeout for an advertisement."""
        controller = await connected(client)
        await client.disconnect()

        with pytest.raises(AirseekersTransportError, match="not connected"):
            await asyncio.wait_for(controller.stop(), timeout=1)
