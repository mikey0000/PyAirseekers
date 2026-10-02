"""The whole exception hierarchy; nothing else in the package defines one."""

from __future__ import annotations


class AirseekersError(Exception):
    """Base class for every error raised by pyairseekers."""


class AirseekersTransportError(AirseekersError):
    """Network failure, timeout, 408/429/5xx, or a body that is not JSON.

    Transient: back off and retry. Never changes credential state.
    """


class AirseekersApiError(AirseekersError):
    """The cloud answered with a non-success envelope code."""

    def __init__(self, message: str, *, code: int | None = None, path: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.path = path


class AirseekersAuthError(AirseekersApiError):
    """The account credentials were rejected.

    Terminal: the client refuses further calls without network I/O until
    the host supplies new credentials (D5).
    """


class AirseekersServiceError(AirseekersApiError):
    """The mower's Foxglove bridge failed or rejected a ROS service call.

    ``code`` carries the service's own result code when it answered with one;
    ``path`` is the service name.
    """
