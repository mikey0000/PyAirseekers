from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from pyairseekers import AirseekersApiError, AirseekersAuthError, AirseekersCloud, AirseekersTransportError
from tests._helpers import EMAIL, PASSWORD, SN

if TYPE_CHECKING:
    from tests.integration.fakeserver.cloud import FakeCloud


def make_cloud(fake: FakeCloud, password: str = PASSWORD) -> AirseekersCloud:
    return AirseekersCloud(EMAIL, password, base_url=fake.state.base_url)


class TestLogin:
    async def test_logs_in_lazily_on_first_call(self, fake_cloud: FakeCloud) -> None:
        async with make_cloud(fake_cloud) as cloud:
            devices = await cloud.get_devices()

        assert devices == [{"sn": SN, "online_status": 1}]
        assert fake_cloud.state.logins == 1

    async def test_switches_to_the_host_named_by_login(self, fake_cloud: FakeCloud) -> None:
        fake_cloud.state.login_host = "https://regional.invalid/"
        async with make_cloud(fake_cloud) as cloud:
            await cloud.login()

            assert cloud.base_url == "https://regional.invalid"

    @pytest.mark.regression
    async def test_trailing_slash_in_base_url_is_ignored(self, fake_cloud: FakeCloud) -> None:
        """A base_url ending in "/" produced "//user/login" and a 404."""
        async with AirseekersCloud(EMAIL, PASSWORD, base_url=fake_cloud.state.base_url + "/") as cloud:
            await cloud.login()

        assert fake_cloud.state.logins == 1

    async def test_rejection_is_terminal_and_skips_the_network(self, fake_cloud: FakeCloud) -> None:
        async with make_cloud(fake_cloud, password="wrong") as cloud:
            with pytest.raises(AirseekersAuthError):
                await cloud.get_devices()
            with pytest.raises(AirseekersAuthError):
                await cloud.get_devices()

        assert fake_cloud.state.logins == 1

    async def test_new_credentials_clear_the_terminal_state(self, fake_cloud: FakeCloud) -> None:
        async with make_cloud(fake_cloud, password="wrong") as cloud:
            with pytest.raises(AirseekersAuthError):
                await cloud.login()
            cloud.set_credentials(EMAIL, PASSWORD)

            assert await cloud.get_devices()


class TestRenewal:
    async def test_expired_token_is_renewed_once_and_the_call_retried(self, fake_cloud: FakeCloud) -> None:
        async with make_cloud(fake_cloud) as cloud:
            await cloud.login()
            fake_cloud.state.expire_token()

            assert await cloud.get_devices()

        assert fake_cloud.state.logins == 2
        assert fake_cloud.state.refreshes == 1

    async def test_refresh_token_is_preferred_over_login(self, fake_cloud: FakeCloud) -> None:
        fake_cloud.state.accept_refresh = True
        async with make_cloud(fake_cloud) as cloud:
            await cloud.login()
            fake_cloud.state.expire_token()

            assert await cloud.get_devices()

        assert fake_cloud.state.logins == 1

    async def test_concurrent_callers_share_one_renewal(self, fake_cloud: FakeCloud) -> None:
        async with make_cloud(fake_cloud) as cloud:
            await cloud.login()
            fake_cloud.state.expire_token()
            fake_cloud.state.login_gate = gate = asyncio.Event()

            calls = [asyncio.create_task(cloud.get_devices()) for _ in range(5)]
            for _ in range(20):
                await asyncio.sleep(0)
            gate.set()
            results = await asyncio.wait_for(asyncio.gather(*calls), timeout=5)

        assert all(results)
        assert fake_cloud.state.logins == 2


class TestErrors:
    async def test_non_json_client_error_is_an_api_error(self, fake_cloud: FakeCloud) -> None:
        async with AirseekersCloud(EMAIL, PASSWORD, base_url=fake_cloud.state.base_url + "/missing") as cloud:
            with pytest.raises(AirseekersApiError) as err:
                await cloud.login()

        assert err.value.code == 404

    async def test_server_error_is_transient_and_keeps_the_token(self, fake_cloud: FakeCloud) -> None:
        async with make_cloud(fake_cloud) as cloud:
            await cloud.login()
            fake_cloud.state.next_status = 503

            with pytest.raises(AirseekersTransportError):
                await cloud.get_devices()
            assert await cloud.get_devices()

        assert fake_cloud.state.logins == 1

    async def test_non_json_body_is_transient(self, fake_cloud: FakeCloud) -> None:
        async with make_cloud(fake_cloud) as cloud:
            await cloud.login()
            fake_cloud.state.next_non_json = True

            with pytest.raises(AirseekersTransportError, match="non-JSON"):
                await cloud.get_devices()

    async def test_rejected_command_carries_the_code(self, fake_cloud: FakeCloud) -> None:
        async with make_cloud(fake_cloud) as cloud:
            with pytest.raises(AirseekersApiError) as err:
                await cloud.dock(SN)

        assert err.value.code == -107

    async def test_unreachable_host_is_transient(self) -> None:
        async with AirseekersCloud(EMAIL, PASSWORD, base_url="http://127.0.0.1:9") as cloud:
            with pytest.raises(AirseekersTransportError):
                await cloud.get_devices()
