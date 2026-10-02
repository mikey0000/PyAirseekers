"""The mower's local HTTP API (``mower_logic``, port 13344, no authentication).

Evidence (``docs/api/local.md``): ``GET /map/list`` verified on a Tron; the
task commands come from the vendor's OpenAPI spec and are used on the owner's
decision without on-device verification (D17). Map writes (``/map/save``,
``/map/delete``, ``/maping/*``) are deliberately not wrapped: ``/map/save``
was seen to repoint the active map.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import aiohttp

from pyairseekers.exceptions import AirseekersApiError, AirseekersTransportError

if TYPE_CHECKING:
    from collections.abc import Mapping

_LOGGER = logging.getLogger(__name__)

DEFAULT_HTTP_PORT = 13344
HTTP_TIMEOUT_S = 10

type JsonObject = dict[str, object]


class LocalApi:
    """Client for the mower's local HTTP API.

    Pass a host-owned ``aiohttp.ClientSession``; the client never closes it.
    """

    def __init__(self, host: str, session: aiohttp.ClientSession, port: int = DEFAULT_HTTP_PORT) -> None:
        self._base = f"http://{host}:{port}"
        self._session = session

    def __repr__(self) -> str:
        return f"LocalApi({self._base!r})"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str | int] | None = None,
        payload: Mapping[str, object] | None = None,
    ) -> object:
        """Send a request and return the envelope's ``data``.

        The envelope is ``{"successed": bool, "errorCode": int, "msg": str,
        "data": ...}``; anything but ``successed`` / ``errorCode == 0`` raises.
        """
        if self._session.closed:
            raise AirseekersTransportError("HTTP session is closed")
        try:
            async with self._session.request(
                method,
                f"{self._base}{path}",
                params=dict(params) if params else None,
                json=dict(payload) if payload is not None else None,
                timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT_S),
            ) as resp:
                status = resp.status
                try:
                    body = await resp.json(content_type=None)
                except ValueError:
                    body = None
        except (aiohttp.ClientError, TimeoutError) as err:
            raise AirseekersTransportError(f"{method} {path}: {err!r}") from err
        _LOGGER.debug("%s %s -> %s", method, path, status)
        if not isinstance(body, dict):
            if status >= 400:
                raise AirseekersApiError(f"{method} {path}: HTTP {status}", code=status, path=path)
            raise AirseekersTransportError(f"{method} {path}: HTTP {status} with a non-JSON body")
        code = body.get("errorCode")
        if body.get("successed") is not True and code != 0:
            raise AirseekersApiError(
                f"{path}: {body.get('msg')}", code=code if isinstance(code, int) else status, path=path
            )
        return body.get("data")

    # Reads, read-only

    async def map_list(self) -> list[JsonObject]:
        """Return the maps stored on the mower, each with ``mapId``, ``mapName`` and GeoJSON ``geoData``.

        Coordinates are in the mower's local frame (metres from the dock).
        """
        data = await self._request("GET", "/map/list")
        return [m for m in data if isinstance(m, dict)] if isinstance(data, list) else []

    async def coverage_path(self) -> object:
        """Return the current task's planned coverage path (GeoJSON)."""
        return await self._request("GET", "/task/getCoveragePath")

    async def walk_path(self, point_index: int = 0) -> object:
        """Return the path driven so far in the current task, from ``point_index``."""
        return await self._request("GET", "/task/getWalkPath", params={"point_index": point_index})

    # Commands, used on the owner's decision (D17)

    async def start_task(self, map_name: str) -> None:
        """Start mowing the named map with the task stored on the mower."""
        await self._request("POST", "/task/start", payload={"mapName": map_name})

    async def pause_task(self) -> None:
        """Pause the current task."""
        await self._request("GET", "/task/pause")

    async def resume_task(self) -> None:
        """Resume the paused task."""
        await self._request("GET", "/task/resume")

    async def stop_task(self) -> None:
        """Stop the current task."""
        await self._request("GET", "/task/stop")

    async def dock(self) -> None:
        """Return to the dock."""
        await self._request("GET", "/task/dock")

    async def undock(self) -> None:
        """Leave the dock."""
        await self._request("GET", "/task/unDock")
