"""Local access to the mower's Foxglove bridge (ws://<mower-ip>:8765)."""

from pyairseekers.local.control import ControllerCommand, MowerController, TriggerResult
from pyairseekers.local.foxglove import Channel, FoxgloveClient, ServerInfo, Service
from pyairseekers.local.http import LocalApi

__all__ = [
    "Channel",
    "ControllerCommand",
    "FoxgloveClient",
    "LocalApi",
    "MowerController",
    "ServerInfo",
    "Service",
    "TriggerResult",
]
