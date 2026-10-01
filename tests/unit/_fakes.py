"""Hand-written fakes with the same interface as the real collaborators."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pyairseekers.exceptions import AirseekersApiError

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping

    from pyairseekers.cloud.transport import Json


@dataclass(frozen=True)
class RecordedRequest:
    """One call made to a ``FakeRequester``."""

    method: str
    path: str
    params: dict[str, object] | None
    payload: dict[str, object] | None


@dataclass
class FakeRequester:
    """Scripted ``Requester``: returns queued ``data`` or raises queued errors, in order."""

    responses: deque[Json | AirseekersApiError] = field(default_factory=deque)
    calls: list[RecordedRequest] = field(default_factory=list)

    def queue(self, *responses: Json | AirseekersApiError) -> None:
        """Append responses for the next calls."""
        self.responses.extend(responses)

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str | int] | None = None,
        payload: Mapping[str, object] | None = None,
        empty_codes: Collection[int] = (),
    ) -> Json:
        self.calls.append(
            RecordedRequest(
                method, path, dict(params) if params else None, dict(payload) if payload is not None else None
            )
        )
        response = self.responses.popleft() if self.responses else None
        if isinstance(response, AirseekersApiError):
            if response.code in empty_codes:
                return None
            raise response
        return response

    @property
    def last(self) -> RecordedRequest:
        """The most recent call."""
        return self.calls[-1]
