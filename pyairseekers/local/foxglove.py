"""Async Foxglove WebSocket client for the Airseekers Tron mower.

The mower runs ros-foxglove-bridge (ROS1 Noetic) on port 8765 with no auth.
Originally written by Shimmi for airseekers-tron-ha (local). Subscribing is
unrestricted. ``call_service`` is a raw primitive: the library's own commands
go only through ``local/control.py`` (D15); a host calling it directly owns
the safety of what it sends. Publishing is not implemented.
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

from pyairseekers.exceptions import AirseekersServiceError, AirseekersTransportError
from pyairseekers.local.ros1 import Typestore, parse_msg_text, to_type_path

_LOGGER = logging.getLogger(__name__)

SUBPROTOCOL = "foxglove.websocket.v1"
CONNECT_TIMEOUT = 10
SERVICE_CALL_TIMEOUT = 5.0
SERVICE_ENCODING = "ros1"
CAPABILITY_SERVICES = "services"

OP_MESSAGE_DATA = 0x01
OP_SERVICE_CALL_REQUEST = 0x02
OP_SERVICE_CALL_RESPONSE = 0x03
MSG_DATA_HEADER_SIZE = 13  # opcode + u32 subscription id + u64 timestamp
SERVICE_HEADER_SIZE = 13  # opcode + u32 service id + u32 call id + u32 encoding length
_CLOSING_TYPES = (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR)


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


@dataclass(frozen=True)
class Service:
    """A single advertised ROS service."""

    id: int
    name: str
    type: str
    request_schema: str
    response_schema: str


type MessageCallback = Callable[[str, str, object], Coroutine[object, object, None]]
type ConnectionCallback = Callable[[bool], Coroutine[object, object, None]]


def decode_schema(raw: object) -> str:
    """Return schema text; the bridge may send it plain or base64-encoded."""
    if not isinstance(raw, str) or not raw:
        return ""
    try:
        return base64.b64decode(raw, validate=True).decode()
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return raw


class FoxgloveClient:
    """Async Foxglove WebSocket v1 client.

    ``connect`` reads serverInfo and the channel advertisement, then runs a
    receive loop that tracks channels and services. ``subscribe`` streams
    decoded ROS1 messages to a callback.
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

        self._services: dict[str, Service] = {}
        self._services_by_id: dict[int, Service] = {}
        self._services_advertised = asyncio.Event()
        self._closed = asyncio.Event()
        self._pending_calls: dict[int, tuple[str, asyncio.Future[bytes]]] = {}
        self._next_call_id = 1

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
    def available_services(self) -> dict[str, Service]:
        """Return the advertised services by name."""
        return dict(self._services)

    @property
    def session_id(self) -> str | None:
        """Return the bridge session id, once connected."""
        return self._server_info.session_id if self._server_info else None

    async def connect(self) -> ServerInfo:
        """Connect, read server info and channels, and start the receive loop.

        Tears down any previous connection first, so a reconnect never leaves
        an old receive loop failing the new connection's calls.

        Raises:
            AirseekersTransportError: the bridge is unreachable or did not
                speak the Foxglove protocol.
        """
        await self.disconnect()
        self._closed.clear()
        url = f"ws://{self._host}:{self._port}"
        if self._session.closed:
            raise AirseekersTransportError(f"Foxglove bridge at {url}: HTTP session is closed")
        try:
            self._ws = await asyncio.wait_for(
                self._session.ws_connect(url, protocols=[SUBPROTOCOL]),
                timeout=CONNECT_TIMEOUT,
            )
            self._server_info = await self._read_server_info()
            await self._read_initial_advertise()
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            # repr: a timeout's str() is empty
            raise AirseekersTransportError(f"Foxglove bridge at {url}: {err!r}") from err
        self._typestore = Typestore()
        self._receive_task = asyncio.create_task(self._receive_loop())
        return self._server_info

    async def subscribe(
        self,
        topics: list[str],
        message_callback: MessageCallback,
        connection_callback: ConnectionCallback | None = None,
    ) -> None:
        """Subscribe to *topics*; decoded messages go to *message_callback*."""
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

        await self._send(self._socket().send_json({"op": "subscribe", "subscriptions": subscriptions}))
        _LOGGER.debug("Subscribed to %d topics", len(subscriptions))

    async def service(self, name: str) -> Service:
        """Return an advertised service, waiting for the advertisement if needed.

        Raises:
            AirseekersTransportError: not connected.
            AirseekersServiceError: the bridge does not offer services, or not
                this one.
        """
        self._socket()
        info = self._server_info
        if info is None or CAPABILITY_SERVICES not in info.capabilities:
            raise AirseekersServiceError("bridge does not offer service calls", path=name)
        if info.supported_encodings and SERVICE_ENCODING not in info.supported_encodings:
            raise AirseekersServiceError(f"bridge does not accept {SERVICE_ENCODING} requests", path=name)
        if name not in self._services:
            await self._wait_for_services()
        if (svc := self._services.get(name)) is None:
            raise AirseekersServiceError("service is not advertised", path=name)
        return svc

    async def _wait_for_services(self) -> None:
        # Stop waiting as soon as the advertisement arrives or the socket drops
        waits = {
            asyncio.ensure_future(self._services_advertised.wait()),
            asyncio.ensure_future(self._closed.wait()),
        }
        try:
            await asyncio.wait(waits, timeout=CONNECT_TIMEOUT, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for wait in waits:
                wait.cancel()
        self._socket()

    async def call_service(self, service: Service, request: bytes) -> bytes:
        """Call an advertised service with a ROS1-serialised request; return the raw response.

        A raw primitive with no knowledge of what the service does. The
        library's own commands use it only from ``local/control.py`` (D15).

        Raises:
            AirseekersServiceError: the bridge reported ``serviceCallFailure``.
            AirseekersTransportError: not connected, the connection dropped,
                or no response within ``SERVICE_CALL_TIMEOUT``.
        """
        call_id = self._next_call_id
        self._next_call_id += 1
        encoding = SERVICE_ENCODING.encode()
        frame = struct.pack("<BIII", OP_SERVICE_CALL_REQUEST, service.id, call_id, len(encoding)) + encoding + request

        future: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()
        self._pending_calls[call_id] = (service.name, future)
        try:
            await self._send(self._socket().send_bytes(frame))
            return await asyncio.wait_for(future, timeout=SERVICE_CALL_TIMEOUT)
        except TimeoutError as err:
            raise AirseekersTransportError(f"{service.name}: no response in {SERVICE_CALL_TIMEOUT} s") from err
        finally:
            self._pending_calls.pop(call_id, None)

    @staticmethod
    async def _send(sending: Coroutine[object, object, None]) -> None:
        try:
            await sending
        except (aiohttp.ClientError, ConnectionError) as err:
            raise AirseekersTransportError(f"Foxglove send failed: {err}") from err

    async def disconnect(self) -> None:
        """Shut down the connection and forget everything it advertised.

        An explicit disconnect does not invoke the connection callback; that
        reports unexpected loss only.
        """
        self._connection_callback = None
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._receive_task
            self._receive_task = None
        self._fail_pending_calls()

        if self._ws and not self._ws.closed:
            await self._ws.close()
        self._ws = None
        self._closed.set()
        self._subscriptions.clear()
        self._next_sub_id = 1
        self._channels.clear()
        self._topic_to_channel.clear()
        self._registered_schemas.clear()
        self._services.clear()
        self._services_by_id.clear()
        self._services_advertised.clear()

    def _socket(self) -> aiohttp.ClientWebSocketResponse:
        if self._ws is None or self._ws.closed:
            raise AirseekersTransportError("Foxglove bridge is not connected")
        return self._ws

    def _fail_pending_calls(self) -> None:
        for _, future in self._pending_calls.values():
            if not future.done():
                future.set_exception(AirseekersTransportError("Foxglove connection closed"))
        self._pending_calls.clear()

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
            self._handle_text(json.loads(msg.data))

    def _process_advertise(self, data: dict[str, object]) -> None:
        channels = data.get("channels")
        for ch in channels if isinstance(channels, list) else []:
            channel = Channel(
                id=ch["id"],
                topic=ch["topic"],
                encoding=ch.get("encoding", "ros1"),
                schema_name=ch["schemaName"],
                schema=decode_schema(ch.get("schema")),
            )
            self._channels[channel.id] = channel
            self._topic_to_channel[channel.topic] = channel

    def _process_advertise_services(self, data: dict[str, object]) -> None:
        services = data.get("services")
        for svc in services if isinstance(services, list) else []:
            # Newer bridges nest schemas under request/response; older ones use flat keys
            request = svc.get("request") or {}
            response = svc.get("response") or {}
            service = Service(
                id=svc["id"],
                name=svc["name"],
                type=svc.get("type", ""),
                request_schema=decode_schema(request.get("schema", svc.get("requestSchema"))),
                response_schema=decode_schema(response.get("schema", svc.get("responseSchema"))),
            )
            self._services[service.name] = service
            self._services_by_id[service.id] = service
        self._services_advertised.set()

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
        ws = self._socket()
        try:
            async for msg in ws:
                if msg.type in _CLOSING_TYPES:
                    break
                await self._handle_frame(msg)
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("Foxglove receive loop error")
        finally:
            self._closed.set()
            self._fail_pending_calls()
            if not ws.closed:
                # So `connected` turns False and hosts reconnect
                await ws.close()
            if self._connection_callback:
                await self._connection_callback(False)  # noqa: FBT003 - the callback type is positional

    async def _handle_frame(self, msg: aiohttp.WSMessage) -> None:
        # One bad frame must not end the stream
        try:
            if msg.type == aiohttp.WSMsgType.TEXT:
                self._handle_text(json.loads(msg.data))
            elif msg.type == aiohttp.WSMsgType.BINARY:
                await self._handle_binary(msg.data)
        except Exception:
            _LOGGER.warning("Dropped a malformed Foxglove frame", exc_info=True)

    def _handle_text(self, data: dict[str, object]) -> None:
        handler = {
            "advertise": self._process_advertise,
            "unadvertise": self._process_unadvertise,
            "advertiseServices": self._process_advertise_services,
            "unadvertiseServices": self._process_unadvertise_services,
            "serviceCallFailure": self._process_service_failure,
            "status": self._process_status,
        }.get(str(data.get("op")))
        if handler is not None:
            handler(data)

    def _process_unadvertise(self, data: dict[str, object]) -> None:
        ids = data.get("channelIds")
        for ch_id in ids if isinstance(ids, list) else []:
            if ch := self._channels.pop(ch_id, None):
                self._topic_to_channel.pop(ch.topic, None)

    def _process_unadvertise_services(self, data: dict[str, object]) -> None:
        ids = data.get("serviceIds")
        for svc_id in ids if isinstance(ids, list) else []:
            if svc := self._services_by_id.pop(svc_id, None):
                self._services.pop(svc.name, None)

    def _process_service_failure(self, data: dict[str, object]) -> None:
        call_id = data.get("callId")
        pending = self._pending_calls.get(call_id) if isinstance(call_id, int) else None
        if pending is not None and not pending[1].done():
            name, future = pending
            future.set_exception(AirseekersServiceError(str(data.get("message", "service call failed")), path=name))

    def _process_status(self, data: dict[str, object]) -> None:
        statuses = data.get("statuses")
        for entry in statuses if isinstance(statuses, list) else []:
            level = entry.get("level", 0)
            text = entry.get("message", "")
            if level >= 2:
                _LOGGER.error("Bridge status: %s", text)
            elif level >= 1:
                _LOGGER.warning("Bridge status: %s", text)

    async def _handle_binary(self, data: bytes) -> None:
        if not data:
            return
        if data[0] == OP_SERVICE_CALL_RESPONSE:
            self._handle_service_response(data)
            return
        if data[0] != OP_MESSAGE_DATA or len(data) < MSG_DATA_HEADER_SIZE:
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

    def _handle_service_response(self, data: bytes) -> None:
        if len(data) < SERVICE_HEADER_SIZE:
            return
        _, call_id, encoding_len = struct.unpack_from("<III", data, 1)
        pending = self._pending_calls.get(call_id)
        if pending is not None and not pending[1].done():
            pending[1].set_result(data[SERVICE_HEADER_SIZE + encoding_len :])
