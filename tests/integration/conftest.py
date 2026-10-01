"""Integration fixtures: fake servers on loopback."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp.test_utils import TestServer
import pytest

from tests.integration.fakeserver.cloud import FakeCloud
from tests.integration.fakeserver.foxglove import FakeBridge

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@pytest.fixture
async def fake_cloud() -> AsyncIterator[FakeCloud]:
    cloud = FakeCloud()
    server = TestServer(cloud.app)
    await server.start_server()
    cloud.state.base_url = str(server.make_url("")).rstrip("/")
    yield cloud
    await server.close()


@pytest.fixture
async def fake_bridge() -> AsyncIterator[tuple[FakeBridge, str, int]]:
    bridge = FakeBridge()
    server = TestServer(bridge.app)
    await server.start_server()
    yield bridge, str(server.host), int(server.port or 0)
    await bridge.outbox.put(None)
    await server.close()
