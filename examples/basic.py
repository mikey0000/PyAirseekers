"""Example: list devices, mint a live-video URL, read local telemetry.

Reads AIRSEEKERS_EMAIL, AIRSEEKERS_PASSWORD and AIRSEEKERS_MOWER_IP.
"""

import asyncio
import logging
import os

import aiohttp

from pyairseekers import AirseekersCloud, FoxgloveClient

logging.basicConfig(level=logging.INFO)

_LOGGER = logging.getLogger("example")


async def on_message(topic: str, schema_name: str, msg: object) -> None:
    """Log each decoded message."""
    _LOGGER.info("%s (%s): %s", topic, schema_name, msg)


async def main() -> None:
    """Run the example."""
    async with aiohttp.ClientSession() as session:
        cloud = AirseekersCloud(os.environ["AIRSEEKERS_EMAIL"], os.environ["AIRSEEKERS_PASSWORD"], session)
        devices = await cloud.get_devices()
        sn = devices[0]["sn"]
        _LOGGER.info("Device %s online: %s", sn, devices[0].get("online_status") == 1)

        # Signed and short-lived; play it with pyairseekers.live.whep_play, never log it
        await cloud.open_live_stream(str(sn), 3)

        local = FoxgloveClient(os.environ["AIRSEEKERS_MOWER_IP"], 8765, session)
        await local.connect()
        await local.subscribe(["/battery", "/fix"], message_callback=on_message)
        await asyncio.sleep(10)
        await local.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
