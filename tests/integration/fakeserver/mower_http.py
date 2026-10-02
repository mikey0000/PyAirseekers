"""aiohttp fake of the mower's local HTTP API (mower_logic, port 13344)."""

from __future__ import annotations

from dataclasses import dataclass, field

from aiohttp import web

MAP = {
    "mapId": "24705761407971328",
    "mapName": "24705761407971328",
    "createTime": "2026-03-30 09:35:12",
    "geoData": {"type": "FeatureCollection", "features": [{"properties": {"type": 1, "name": "A", "id": "a1"}}]},
}


def envelope(data: object = None, *, code: int = 0, msg: str = "successed") -> dict[str, object]:
    """Build a mower_logic response envelope."""
    return {"successed": code == 0, "errorCode": code, "msg": msg, "data": data}


@dataclass
class MowerHttpState:
    """Server-side state and fault knobs."""

    error_code: int = 0
    non_json: bool = False
    calls: list[tuple[str, str, object]] = field(default_factory=list)


class FakeMowerHttp:
    """Answers every documented endpoint; records what it was sent."""

    def __init__(self) -> None:
        self.state = MowerHttpState()
        self.app = web.Application()
        self.app.router.add_route("*", "/{tail:.*}", self._handle)

    async def _handle(self, request: web.Request) -> web.Response:
        body = await request.json() if request.can_read_body else dict(request.query)
        self.state.calls.append((request.method, request.path, body))
        if self.state.non_json:
            return web.Response(text="<html>busy</html>")
        if self.state.error_code:
            return web.json_response(envelope(code=self.state.error_code, msg="no task running"))
        if request.path == "/map/list":
            return web.json_response(envelope([MAP, "not-a-map"]))
        return web.json_response(envelope())
