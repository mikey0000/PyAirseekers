"""Verified local controller commands over the Foxglove bridge (D15).

Only ``/controller/ctrl`` with ``stop`` and ``pause`` is sanctioned: its
schema was read from the bridge and safe-stop was verified on a mower.
``resume`` sets a bladed mower moving and waits for its own on-device
verification (Q16). Each call checks the advertised schemas are still the
verified ones and that the controller answered ``result == 0``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import struct
from typing import TYPE_CHECKING

from pyairseekers.exceptions import AirseekersServiceError
from pyairseekers.local.ros1 import encode_string, schema_fields

if TYPE_CHECKING:
    from pyairseekers.local.foxglove import FoxgloveClient, Service

CONTROLLER_SERVICE = "/controller/ctrl"
TRIGGER_REQUEST_FIELDS = ["string arg"]
TRIGGER_RESPONSE_FIELDS = ["int32 result", "string message"]
TRIGGER_SUCCESS = 0
_TRIGGER_HEADER = 8  # int32 result + uint32 message length


class ControllerCommand(StrEnum):
    """Verified ``/controller/ctrl`` arguments."""

    STOP = "stop"
    PAUSE = "pause"


@dataclass(frozen=True)
class TriggerResult:
    """The controller's answer to an accepted command."""

    result: int
    message: str


class MowerController:
    """Send verified controller commands to the mower over its local bridge."""

    def __init__(self, client: FoxgloveClient) -> None:
        self._client = client

    async def stop(self) -> TriggerResult:
        """Stop the mower's controller (verified safe-stop).

        Raises:
            AirseekersServiceError: the schema changed, the call failed, or
                the controller answered non-zero (e.g. nothing to stop).
            AirseekersTransportError: not connected, or no answer in time.
        """
        return await self._trigger(ControllerCommand.STOP)

    async def pause(self) -> TriggerResult:
        """Pause the mower's controller. Raises as ``stop``."""
        return await self._trigger(ControllerCommand.PAUSE)

    async def _trigger(self, command: ControllerCommand) -> TriggerResult:
        service = await self._client.service(CONTROLLER_SERVICE)
        _require_verified_schema(service)
        raw = await self._client.call_service(service, encode_string(command.value))
        result = _decode_trigger_response(raw, service.name)
        if result.result != TRIGGER_SUCCESS:
            raise AirseekersServiceError(
                f"{command.value} rejected: {result.message}", code=result.result, path=service.name
            )
        return result


def _require_verified_schema(service: Service) -> None:
    # A firmware update that changes the schema must not be driven blind
    if (
        schema_fields(service.request_schema) != TRIGGER_REQUEST_FIELDS
        or schema_fields(service.response_schema) != TRIGGER_RESPONSE_FIELDS
    ):
        raise AirseekersServiceError("schema differs from the verified Trigger schema", path=service.name)


def _decode_trigger_response(raw: bytes, name: str) -> TriggerResult:
    length = struct.unpack_from("<I", raw, 4)[0] if len(raw) >= _TRIGGER_HEADER else None
    if length is None or len(raw) < _TRIGGER_HEADER + length:
        raise AirseekersServiceError("malformed Trigger response: truncated", path=name)
    (result,) = struct.unpack_from("<i", raw, 0)
    try:
        message = raw[_TRIGGER_HEADER : _TRIGGER_HEADER + length].decode()
    except UnicodeDecodeError:
        raise AirseekersServiceError("malformed Trigger response: message is not UTF-8", path=name) from None
    return TriggerResult(result=result, message=message)
