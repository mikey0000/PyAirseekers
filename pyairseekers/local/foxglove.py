"""Async Foxglove WebSocket client for the Airseekers Tron mower.

The mower runs ros-foxglove-bridge (ROS1 Noetic) on port 8765 with no auth.
Originally written by Shimmi for airseekers-tron-ha (local).
"""

from __future__ import annotations

import asyncio
import base64
import binascii
from collections.abc import Callable, Coroutine
import contextlib
from dataclasses import dataclass, field
import json
import logging
import struct

import aiohttp

from pyairseekers.exceptions import AirseekersTransportError
from pyairseekers.local.ros1 import Typestore, parse_msg_text, to_type_path

_LOGGER = logging.getLogger(__name__)

SUBPROTOCOL = "foxglove.websocket.v1"
CONNECT_TIMEOUT = 10
MSG_DATA_HEADER_SIZE = 13  # 1 opcode + 4 sub_id + 8 timestamp


@dataclass(frozen=True)
class ServerInfo:
    """Foxglove server information received on connect."""

    name: str
    capabilities: tuple[str, ...]
    supported_encodings: tuple[str, ...]
    session_id: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Channel:
    """A single advertised Foxglove channel (topic)."""

    id: int
    topic: str
    encoding: str
    schema_name: str
    schema: str


type MessageCallback = Callable[[str, str, object], Coroutine[object, object, None]]
type ConnectionCallback = Callable[[bool], Coroutine[object, object, None]]


class FoxgloveClient:
    """Async Foxglove WebSocket v1 client.

    Connects to the mower's ros-foxglove-bridge, subscribes to topics, and
    streams decoded ROS1 messages via *message_callback*.
    """

    def __init__(
        self,
        host: str,
        port: int,
        session: aiohttp.ClientSession,
    ) -> None:
        self._host = host
        self._port = port
        self._session = session

        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._receive_task: asyncio.Task[None] | None = None

        self._server_info: ServerInfo | None = None
        self._channels: dict[int, Channel] = {}
        self._topic_to_channel: dict[str, Channel] = {}
        self._subscriptions: dict[int, int] = {}  # sub_id → channel_id
        self._next_sub_id = 1

        self._message_callback: MessageCallback | None = None
        self._connection_callback: ConnectionCallback | None = None

        self._typestore: Typestore | None = None
        self._registered_schemas: set[str] = set()

    @property
    def connected(self) -> bool:
        """Return True while the WebSocket is open."""
        return self._ws is not None and not self._ws.closed

    @property
    def server_info(self) -> ServerInfo | None:
        """Return the bridge's serverInfo, once connected."""
        return self._server_info

    @property
    def available_topics(self) -> dict[str, Channel]:
        """Return the advertised channels by topic."""
        return dict(self._topic_to_channel)

    @property
    def session_id(self) -> str | None:
        """Return the bridge session id, once connected."""
        return self._server_info.session_id if self._server_info else None

    async def connect(self) -> ServerInfo:
        """Connect to the Foxglove bridge and read server info and channels.

        Raises:
            AirseekersTransportError: the bridge is unreachable or did not
                speak the Foxglove protocol.
        """
        url = f"ws://{self._host}:{self._port}"
        try:
            self._ws = await asyncio.wait_for(
                self._session.ws_connect(url, protocols=[SUBPROTOCOL]),
                timeout=CONNECT_TIMEOUT,
            )
            self._server_info = await self._read_server_info()
            await self._read_initial_advertise()
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise AirseekersTransportError(f"Foxglove bridge at {url}: {err}") from err
        self._typestore = Typestore()
        return self._server_info

    async def subscribe(
        self,
        topics: list[str],
        message_callback: MessageCallback,
        connection_callback: ConnectionCallback | None = None,
    ) -> None:
        """Subscribe to *topics* and start the receive loop."""
        self._message_callback = message_callback
        self._connection_callback = connection_callback

        subscriptions: list[dict[str, int]] = []
        for topic in topics:
            channel = self._topic_to_channel.get(topic)
            if channel is None:
                _LOGGER.debug("Topic %s not advertised, skipping", topic)
                continue
            self._register_schema(channel)
            sub_id = self._next_sub_id
            self._next_sub_id += 1
            self._subscriptions[sub_id] = channel.id
            subscriptions.append({"id": sub_id, "channelId": channel.id})

        if not subscriptions:
            _LOGGER.warning("No topics matched any advertised channel")
            return

        await self._socket().send_json({"op": "subscribe", "subscriptions": subscriptions})
        _LOGGER.debug("Subscribed to %d topics", len(subscriptions))
        self._receive_task = asyncio.create_task(self._receive_loop())

    async def disconnect(self) -> None:
        """Cleanly shut down the connection."""
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._receive_task
            self._receive_task = None

        if self._ws and not self._ws.closed:
            await self._ws.close()
        self._ws = None
        self._subscriptions.clear()
        self._next_sub_id = 1

    def _socket(self) -> aiohttp.ClientWebSocketResponse:
        if self._ws is None:
            raise AirseekersTransportError("Foxglove bridge is not connected")
        return self._ws

    async def _read_server_info(self) -> ServerInfo:
        msg = await asyncio.wait_for(self._socket().receive(), timeout=CONNECT_TIMEOUT)
        if msg.type != aiohttp.WSMsgType.TEXT:
            raise AirseekersTransportError(f"Expected serverInfo text, got {msg.type}")
        data = json.loads(msg.data)
        if data.get("op") != "serverInfo":
            raise AirseekersTransportError(f"Expected serverInfo, got op={data.get('op')}")
        return ServerInfo(
            name=data.get("name", ""),
            capabilities=tuple(data.get("capabilities", ())),
            supported_encodings=tuple(data.get("supportedEncodings", ())),
            session_id=data.get("sessionId", ""),
            metadata=data.get("metadata", {}),
        )

    async def _read_initial_advertise(self) -> None:
        msg = await asyncio.wait_for(self._socket().receive(), timeout=CONNECT_TIMEOUT)
        if msg.type == aiohttp.WSMsgType.TEXT:
            data = json.loads(msg.data)
            if data.get("op") == "advertise":
                self._process_advertise(data)

    def _process_advertise(self, data: dict[str, object]) -> None:
        channels = data.get("channels")
        for ch in channels if isinstance(channels, list) else []:
            schema_raw = ch.get("schema", "")
            try:
                schema_text = base64.b64decode(schema_raw).decode()
            except (binascii.Error, UnicodeDecodeError, ValueError):
                schema_text = schema_raw

            channel = Channel(
                id=ch["id"],
                topic=ch["topic"],
                encoding=ch.get("encoding", "ros1"),
                schema_name=ch["schemaName"],
                schema=schema_text,
            )
            self._channels[channel.id] = channel
            self._topic_to_channel[channel.topic] = channel

    def _register_schema(self, channel: Channel) -> None:
        if channel.schema_name in self._registered_schemas:
            return
        if not channel.schema or self._typestore is None:
            return
        try:
            add_types = parse_msg_text(channel.schema, channel.schema_name)
            self._typestore.register(add_types)
            self._registered_schemas.add(channel.schema_name)
        except Exception:
            _LOGGER.warning("Failed to register schema for %s", channel.schema_name, exc_info=True)

    def _deserialize(self, channel: Channel, payload: bytes) -> object | None:
        if self._typestore is None:
            return None
        type_path = to_type_path(channel.schema_name)
        try:
            return self._typestore.deserialize_ros1(payload, type_path)
        except KeyError:
            _LOGGER.debug("Type %s not in typestore", type_path)
        except Exception:
            _LOGGER.debug("Deserialize failed for %s", channel.topic, exc_info=True)
        return None

    async def _receive_loop(self) -> None:
        try:
            async for msg in self._socket():
                if msg.type == aiohttp.WSMsgType.TEXT:
                    self._handle_text(json.loads(msg.data))
                elif msg.type == aiohttp.WSMsgType.BINARY:
                    await self._handle_binary(msg.data)
                elif msg.type in (
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSING,
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.ERROR,
                ):
                    break
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("Foxglove receive loop error")
        finally:
            if self._connection_callback:
                await self._connection_callback(False)  # noqa: FBT003 - the callback type is positional

    def _handle_text(self, data: dict[str, object]) -> None:
        op = data.get("op")
        if op == "advertise":
            self._process_advertise(data)
        elif op == "unadvertise":
            ids = data.get("channelIds")
            for ch_id in ids if isinstance(ids, list) else []:
                ch = self._channels.pop(ch_id, None)
                if ch:
                    self._topic_to_channel.pop(ch.topic, None)
        elif op == "status":
            statuses = data.get("statuses")
            for entry in statuses if isinstance(statuses, list) else []:
                lvl = entry.get("level", 0)
                text = entry.get("message", "")
                if lvl >= 2:
                    _LOGGER.error("Bridge status: %s", text)
                elif lvl >= 1:
                    _LOGGER.warning("Bridge status: %s", text)

    async def _handle_binary(self, data: bytes) -> None:
        if len(data) < MSG_DATA_HEADER_SIZE:
            return
        opcode = data[0]
        if opcode != 0x01:
            return

        sub_id = struct.unpack_from("<I", data, 1)[0]
        payload = data[MSG_DATA_HEADER_SIZE:]

        channel_id = self._subscriptions.get(sub_id)
        if channel_id is None:
            return
        channel = self._channels.get(channel_id)
        if channel is None:
            return

        decoded = self._deserialize(channel, payload)
        if decoded is not None and self._message_callback:
            await self._message_callback(channel.topic, channel.schema_name, decoded)
