from __future__ import annotations

from typing import TYPE_CHECKING

import aiohttp
import pytest

from pyairseekers import AirseekersApiError, AirseekersCloud, whep_play, whep_stop
from tests._helpers import ANSWER_SDP, EMAIL, OFFER_SDP, PASSWORD, SN

if TYPE_CHECKING:
    from tests.integration.fakeserver.cloud import FakeCloud


class TestWhep:
    async def test_open_play_and_stop(self, fake_cloud: FakeCloud) -> None:
        async with (
            AirseekersCloud(EMAIL, PASSWORD, base_url=fake_cloud.state.base_url) as cloud,
            aiohttp.ClientSession() as session,
        ):
            url = await cloud.open_live_stream(SN, 3)
            stream = await whep_play(session, url, OFFER_SDP)
            await whep_stop(session, stream)

        assert stream.answer_sdp == ANSWER_SDP
        assert fake_cloud.state.whep_deleted == ["/rtc/v1/whep/session/abc"]

    async def test_rejected_offer_reports_status_not_url(self, fake_cloud: FakeCloud) -> None:
        url = f"{fake_cloud.state.base_url}/rtc/v1/whep/?secret=wrong-secret"
        async with aiohttp.ClientSession() as session:
            with pytest.raises(AirseekersApiError) as err:
                await whep_play(session, url, OFFER_SDP)

        assert err.value.code == 403
        assert "wrong-secret" not in str(err.value)
