"""WHEP playback against the vendor's SRS media server.

``AirseekersCloud.open_live_stream`` returns a standard WHEP endpoint (SRS 6):
POST a recvonly SDP offer as ``application/sdp``, get the answer back. SRS is
ICE-lite with its candidates in the answer, so no trickle ICE is needed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urljoin

import aiohttp

from pyairseekers.const import WHEP_TIMEOUT_S
from pyairseekers.exceptions import AirseekersApiError, AirseekersTransportError
from pyairseekers.models import LiveStream

if TYPE_CHECKING:
    import logging

_TIMEOUT = aiohttp.ClientTimeout(total=WHEP_TIMEOUT_S)


async def whep_play(session: aiohttp.ClientSession, whep_url: str, offer_sdp: str) -> LiveStream:
    """Send an SDP offer to a WHEP endpoint and return the answer.

    Raises:
        AirseekersTransportError: network failure or timeout.
        AirseekersApiError: the server refused the offer.
    """
    try:
        async with session.post(
            whep_url, data=offer_sdp, headers={"Content-Type": "application/sdp"}, timeout=_TIMEOUT
        ) as resp:
            body = await resp.text()
            location = resp.headers.get("Location")
            status = resp.status
    except (aiohttp.ClientError, TimeoutError) as err:
        raise AirseekersTransportError(f"WHEP offer failed: {err}") from err
    if status not in {200, 201} or not body.startswith("v=0"):
        # The URL carries a signed secret; report the status, never the URL
        raise AirseekersApiError(f"WHEP offer rejected: HTTP {status}", code=status)
    return LiveStream(answer_sdp=body, resource_url=urljoin(whep_url, location) if location else None)


async def whep_stop(session: aiohttp.ClientSession, stream: LiveStream, logger: logging.Logger | None = None) -> None:
    """Tear down a WHEP session; failures are only logged (close path)."""
    if not stream.resource_url:
        return
    try:
        async with session.delete(stream.resource_url, timeout=_TIMEOUT):
            pass
    except (aiohttp.ClientError, TimeoutError) as err:
        if logger is not None:
            logger.debug("WHEP teardown failed: %s", err)
