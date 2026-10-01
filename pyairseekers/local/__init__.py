"""Local access to the mower's Foxglove bridge (ws://<mower-ip>:8765)."""

from pyairseekers.local.foxglove import Channel, FoxgloveClient, ServerInfo

__all__ = ["Channel", "FoxgloveClient", "ServerInfo"]
