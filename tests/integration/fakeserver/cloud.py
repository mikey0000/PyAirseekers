"""aiohttp fake of the Airseekers cloud and SRS WHEP server, with fault knobs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from aiohttp import web

from pyairseekers.const import API_LIVE_OPEN, API_LOGIN, API_REFRESH_TOKEN
from tests._helpers import (
    ACCESS_TOKEN,
    ANSWER_SDP,
    LIVE_SECRET,
    OFFER_SDP,
    PASSWORD,
    REFRESH_TOKEN,
    SN,
    envelope,
)

if TYPE_CHECKING:
    import asyncio

WHEP_PATH = "/rtc/v1/whep/"
WHEP_SESSION = "/rtc/v1/whep/session/abc"


@dataclass
class CloudState:
    """Server-side state and fault knobs."""

    base_url: str = ""
    login_host: str | None = None
    token: str = ACCESS_TOKEN
    token_serial: int = 1
    accept_refresh: bool = False
    next_status: int | None = None
    next_non_json: bool = False
    login_gate: asyncio.Event | None = None
    logins: int = 0
    refreshes: int = 0
    requests: list[tuple[str, str, object]] = field(default_factory=list)
    whep_deleted: list[str] = field(default_factory=list)

    def expire_token(self) -> None:
        """Invalidate the current token server-side."""
        self.token_serial += 1
        self.token = f"{ACCESS_TOKEN}-{self.token_serial}"


class FakeCloud:
    """The fake application; ``state`` is the control surface for tests."""

    def __init__(self) -> None:
        self.state = CloudState()
        self.app = web.Application()
        self.app.router.add_post(API_LOGIN, self._login)
        self.app.router.add_post(API_REFRESH_TOKEN, self._refresh)
        self.app.router.add_post(WHEP_PATH, self._whep_offer)
        self.app.router.add_delete(WHEP_SESSION, self._whep_delete)
        self.app.router.add_route("*", "/api/{tail:.*}", self._api)

    async def _login(self, request: web.Request) -> web.Response:
        self.state.logins += 1
        if self.state.login_gate is not None:
            await self.state.login_gate.wait()
        body = await request.json()
        if body.get("password") != PASSWORD:
            return web.json_response(envelope(code=1001, msg="wrong password"))
        return web.json_response(
            envelope(
                {
                    "access_token": self.state.token,
                    "refresh_token": REFRESH_TOKEN,
                    "host": self.state.login_host or self.state.base_url,
                }
            )
        )

    async def _refresh(self, request: web.Request) -> web.Response:
        self.state.refreshes += 1
        body = await request.json()
        if not self.state.accept_refresh or body.get("refresh_token") != REFRESH_TOKEN:
            return web.json_response(envelope(code=1002, msg="refresh not allowed"))
        return web.json_response(envelope({"access_token": self.state.token}))

    async def _api(self, request: web.Request) -> web.Response:
        body = await request.json() if request.can_read_body else dict(request.query)
        self.state.requests.append((request.method, request.path, body))
        if (status := self.state.next_status) is not None:
            self.state.next_status = None
            return web.Response(status=status, text="busy")
        if self.state.next_non_json:
            self.state.next_non_json = False
            return web.Response(status=200, text="<html>oops</html>")
        if request.headers.get("authorization") != f"Bearer {self.state.token}":
            return web.json_response(envelope(code=401, msg="illegal token"))
        if request.path == "/api/web/device":
            return web.json_response(envelope({"list": [{"sn": SN, "online_status": 1}], "total": 1}))
        if request.path == API_LIVE_OPEN:
            url = f"{self.state.base_url}{WHEP_PATH}?app=live&stream={SN}_{body['camera']}&secret={LIVE_SECRET}"
            return web.json_response(envelope({"url": url}))
        if request.path == "/api/web/device/task/dock":
            return web.json_response(envelope(code=-107, msg="operation not allowed"))
        return web.json_response(envelope({}))

    async def _whep_offer(self, request: web.Request) -> web.Response:
        if request.content_type != "application/sdp" or await request.text() != OFFER_SDP:
            return web.Response(status=400, text="bad offer")
        if request.query.get("secret") != LIVE_SECRET:
            return web.Response(status=403, text="bad secret")
        return web.Response(status=201, text=ANSWER_SDP, headers={"Location": WHEP_SESSION})

    async def _whep_delete(self, request: web.Request) -> web.Response:
        self.state.whep_deleted.append(request.path)
        return web.Response()
