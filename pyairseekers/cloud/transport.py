"""Cloud transport: tokens, HTTP, and mapping responses to data or exceptions."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import TYPE_CHECKING, Protocol, Self

import aiohttp

from pyairseekers.const import (
    API_LOGIN,
    API_REFRESH_TOKEN,
    API_SERVER_HOST,
    APP_VERSION,
    AUTH_ERROR_KEYWORDS,
    REQUEST_TIMEOUT_S,
    SUCCESS_CODE,
)
from pyairseekers.exceptions import AirseekersApiError, AirseekersAuthError, AirseekersTransportError

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping

_LOGGER = logging.getLogger(__name__)

type Json = dict[str, object] | list[object] | str | int | float | bool | None


class Requester(Protocol):
    """What the API layer needs from a transport."""

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str | int] | None = None,
        payload: Mapping[str, object] | None = None,
        empty_codes: Collection[int] = (),
    ) -> Json:
        """Send an authenticated request and return the envelope's ``data``.

        A code in ``empty_codes`` is a documented "nothing here" answer and
        returns ``data`` instead of raising (D6).
        """
        ...


def is_transient_status(status: int) -> bool:
    """Return True for HTTP statuses that mean "try again later"."""
    return status in {408, 429} or status >= 500


def fingerprint(token: str | None) -> str:
    """Return a log-safe identifier for a token."""
    return hashlib.sha256(token.encode()).hexdigest()[:8] if token else "none"


class CloudTransport:
    """Authenticated JSON transport for the Airseekers cloud.

    Owns the access token. One reactive refresh per stale token: concurrent
    callers that hit the same dead token share it (D5).
    """

    def __init__(
        self,
        email: str,
        password: str,
        session: aiohttp.ClientSession | None,
        base_url: str,
    ) -> None:
        self._email = email
        self._password = password
        self._session = session
        self._owns_session = session is None
        self.base_url = base_url.rstrip("/")
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._rejected = False
        self._lock = asyncio.Lock()

    def __repr__(self) -> str:
        return f"CloudTransport(base_url={self.base_url!r}, token={fingerprint(self._access_token)})"

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the HTTP session if this transport created it."""
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    def set_credentials(self, email: str, password: str) -> None:
        """Replace rejected credentials; clears the terminal state."""
        self._email = email
        self._password = password
        self._rejected = False
        self._access_token = self._refresh_token = None

    def _http(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    def _headers(self, token: str | None) -> dict[str, str]:
        headers = {
            "accept": "application/json,*/*",
            "accept-language": "en-US",
            "app-version": APP_VERSION,
            "content-type": "application/json",
        }
        if token:
            headers["authorization"] = f"Bearer {token}"
        return headers

    async def _send(
        self,
        method: str,
        path: str,
        *,
        token: str | None,
        params: Mapping[str, str | int] | None = None,
        payload: Mapping[str, object] | None = None,
    ) -> tuple[int, dict[str, object]]:
        """One HTTP exchange; transient failures raise, everything else returns."""
        try:
            async with self._http().request(
                method,
                f"{self.base_url}{path}",
                params=dict(params) if params else None,
                json=dict(payload) if payload is not None else None,
                headers=self._headers(token),
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_S),
            ) as resp:
                if is_transient_status(resp.status):
                    raise AirseekersTransportError(f"{method} {path}: HTTP {resp.status}")
                try:
                    body = await resp.json(content_type=None)
                except ValueError:
                    body = None
        except (aiohttp.ClientError, TimeoutError) as err:
            raise AirseekersTransportError(f"{method} {path}: {err}") from err
        _LOGGER.debug("%s %s -> %s", method, path, resp.status)
        if isinstance(body, dict):
            return resp.status, body
        if resp.status == 401:
            return resp.status, {}
        if resp.status >= 400:
            raise AirseekersApiError(f"{method} {path}: HTTP {resp.status}", code=resp.status, path=path)
        raise AirseekersTransportError(f"{method} {path}: HTTP {resp.status} with a non-JSON body")

    @staticmethod
    def _is_auth_failure(status: int, body: Mapping[str, object]) -> bool:
        if status == 401:
            return True
        msg = str(body.get("msg", "")).lower()
        return body.get("code") != SUCCESS_CODE and any(kw in msg for kw in AUTH_ERROR_KEYWORDS)

    async def get_server_host(self) -> str:
        """Look up the regional API host and switch to it."""
        _, body = await self._send("GET", API_SERVER_HOST, token=None)
        data = body.get("data")
        host = data.get("host") if isinstance(data, dict) else None
        if body.get("code") != SUCCESS_CODE or not isinstance(host, str):
            raise AirseekersApiError("server-host lookup failed", code=_code(body), path=API_SERVER_HOST)
        self._set_base_url(host)
        return self.base_url

    def _set_base_url(self, host: object) -> None:
        if isinstance(host, str) and host.startswith("http"):
            self.base_url = host.rstrip("/")

    async def login(self) -> None:
        """Log in with email and password. A rejection is terminal (D5)."""
        if self._rejected:
            raise AirseekersAuthError("credentials were rejected; supply new ones", path=API_LOGIN)
        _, body = await self._send(
            "POST", API_LOGIN, token=None, payload={"email": self._email, "password": self._password}
        )
        data = body.get("data")
        if body.get("code") != SUCCESS_CODE or not isinstance(data, dict) or "access_token" not in data:
            # Q3: login failure codes are not catalogued; any non-success is treated as a rejection
            self._rejected = True
            raise AirseekersAuthError(f"login rejected: {body.get('msg')}", code=_code(body), path=API_LOGIN)
        self._access_token = str(data["access_token"])
        refresh = data.get("refresh_token")
        self._refresh_token = str(refresh) if refresh else None
        # D7: the login response names the account's regional host
        self._set_base_url(data.get("host"))
        _LOGGER.info("Logged in to Airseekers cloud (token %s)", fingerprint(self._access_token))

    async def _refresh(self) -> bool:
        if not self._refresh_token:
            return False
        _, body = await self._send(
            "POST", API_REFRESH_TOKEN, token=self._access_token, payload={"refresh_token": self._refresh_token}
        )
        data = body.get("data")
        token = data.get("access_token") if isinstance(data, dict) else None
        if body.get("code") != SUCCESS_CODE or not isinstance(token, str):
            _LOGGER.warning("Refresh token rejected; logging in again")
            return False
        self._access_token = token
        return True

    async def _token(self, stale: str | None = None) -> str:
        """Return a usable token, renewing at most once per stale token."""
        if self._rejected:
            raise AirseekersAuthError("credentials were rejected; supply new ones")
        if self._access_token and self._access_token != stale:
            return self._access_token
        async with self._lock:
            # Another caller may have renewed while we waited
            if self._access_token and self._access_token != stale:
                return self._access_token
            if not (stale and await self._refresh()):
                await self.login()
            if self._access_token is None:
                raise AirseekersAuthError("login returned no token", path=API_LOGIN)
            return self._access_token

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str | int] | None = None,
        payload: Mapping[str, object] | None = None,
        empty_codes: Collection[int] = (),
    ) -> Json:
        """Send an authenticated request and return the envelope's ``data``."""
        token = await self._token()
        status, body = await self._send(method, path, token=token, params=params, payload=payload)
        if self._is_auth_failure(status, body):
            token = await self._token(stale=token)
            status, body = await self._send(method, path, token=token, params=params, payload=payload)
            if self._is_auth_failure(status, body):
                raise AirseekersApiError("token rejected after renewal", code=_code(body) or status, path=path)
        code = _code(body)
        if code != SUCCESS_CODE and code not in empty_codes:
            raise AirseekersApiError(f"{path}: {body.get('msg')}", code=code, path=path)
        data = body.get("data")
        return data if isinstance(data, (dict, list, str, int, float, bool)) else None


def _code(body: Mapping[str, object]) -> int | None:
    code = body.get("code")
    return code if isinstance(code, int) else None
