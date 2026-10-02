from __future__ import annotations

from typing import TYPE_CHECKING

import aiohttp
import pytest

from pyairseekers import AirseekersApiError, AirseekersTransportError, LocalApi

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from tests.integration.fakeserver.mower_http import FakeMowerHttp

type Mower = tuple[FakeMowerHttp, str, int]


@pytest.fixture
async def api(fake_mower_http: Mower) -> AsyncIterator[LocalApi]:
    _, host, port = fake_mower_http
    async with aiohttp.ClientSession() as session:
        yield LocalApi(host, session, port)


class TestReads:
    async def test_map_list_returns_the_maps(self, api: LocalApi) -> None:
        maps = await api.map_list()

        assert [m["mapId"] for m in maps] == ["24705761407971328"]

    async def test_walk_path_sends_the_index(self, api: LocalApi, fake_mower_http: Mower) -> None:
        mower, _, _ = fake_mower_http

        await api.walk_path(5)

        assert mower.state.calls[-1] == ("GET", "/task/getWalkPath", {"point_index": "5"})


class TestCommands:
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("pause_task", "/task/pause"),
            ("resume_task", "/task/resume"),
            ("stop_task", "/task/stop"),
            ("dock", "/task/dock"),
            ("undock", "/task/unDock"),
        ],
    )
    async def test_get_commands_hit_their_path(
        self, api: LocalApi, fake_mower_http: Mower, method: str, path: str
    ) -> None:
        mower, _, _ = fake_mower_http

        await getattr(api, method)()

        assert mower.state.calls[-1][:2] == ("GET", path)

    async def test_start_posts_the_map_name(self, api: LocalApi, fake_mower_http: Mower) -> None:
        mower, _, _ = fake_mower_http

        await api.start_task("garden")

        assert mower.state.calls[-1] == ("POST", "/task/start", {"mapName": "garden"})

    def test_map_writes_are_not_offered(self) -> None:
        assert not any(hasattr(LocalApi, name) for name in ("map_save", "save_map", "map_delete", "delete_map"))


class TestErrors:
    async def test_error_envelope_raises_with_the_code(self, api: LocalApi, fake_mower_http: Mower) -> None:
        mower, _, _ = fake_mower_http
        mower.state.error_code = 501

        with pytest.raises(AirseekersApiError, match="no task running") as err:
            await api.pause_task()

        assert (err.value.code, err.value.path) == (501, "/task/pause")

    async def test_non_json_body_is_transient(self, api: LocalApi, fake_mower_http: Mower) -> None:
        mower, _, _ = fake_mower_http
        mower.state.non_json = True

        with pytest.raises(AirseekersTransportError, match="non-JSON"):
            await api.stop_task()

    async def test_unreachable_mower_is_a_transport_error(self) -> None:
        async with aiohttp.ClientSession() as session:
            with pytest.raises(AirseekersTransportError):
                await LocalApi("127.0.0.1", session, 9).stop_task()

    async def test_closed_session_is_a_transport_error(self) -> None:
        session = aiohttp.ClientSession()
        await session.close()

        with pytest.raises(AirseekersTransportError, match="session is closed"):
            await LocalApi("127.0.0.1", session, 9).map_list()
