"""Cloud API: one method per endpoint over a ``Requester``.

Status of each endpoint (verified on hardware, observed, unverified) is in
``docs/api/cloud.md``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

from pyairseekers.cloud.transport import CloudTransport
from pyairseekers.const import (
    API_BASE_URL,
    API_CLEAN_WARN,
    API_CONFIG,
    API_DEVICE_BIND,
    API_DEVICE_LOCK,
    API_DEVICE_MAP,
    API_DEVICE_MAP_V2,
    API_DEVICE_UNBIND,
    API_DEVICE_UNLOCK,
    API_DEVICES,
    API_EXPLORE_MAP_LATEST,
    API_EXTENDED_WARRANTY,
    API_FILL_LIGHT,
    API_FIRMWARE_LATEST,
    API_FIRMWARE_UPGRADE,
    API_FULL_STATUS,
    API_IOT_CERT,
    API_IS_AUTHORIZED,
    API_LIVE_CAMERA_PARAMS,
    API_LIVE_HEARTBEAT,
    API_LIVE_MOVE_CONTROL,
    API_LIVE_OPEN,
    API_MAINTENANCE_LIST,
    API_MAP_GEO_DATA,
    API_MAP_SWITCH,
    API_NOTIFY_LIST,
    API_NRTK_SUPPORTED,
    API_RTK_INFO,
    API_RTK_REBOOT,
    API_SIM_ACTIVATION_STATUS,
    API_SIM_PACKAGE_INFO,
    API_TASK,
    API_TASK_DOCK,
    API_TASK_LATEST,
    API_TASK_PAUSE,
    API_TASK_RECORD_LATEST,
    API_TASK_RECORD_LIST,
    API_TASK_RESUME,
    API_TASK_START,
    API_TASK_STOP,
    API_VOICE_VERSION,
    API_WARRANTY,
    CODE_ALREADY_LATEST,
    CODE_NO_EXTENDED_WARRANTY,
    CUT_HEIGHT_MAX_MM,
    CUT_HEIGHT_MIN_MM,
)
from pyairseekers.exceptions import AirseekersApiError
from pyairseekers.models import IoTCert

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    import aiohttp

    from pyairseekers.cloud.transport import Json, Requester

type JsonObject = dict[str, object]


def _obj(data: object) -> JsonObject:
    return data if isinstance(data, dict) else {}


def _list(data: object) -> list[JsonObject]:
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


class AirseekersCloud:
    """Async client for the Airseekers cloud REST API.

    Pass a host-owned ``aiohttp.ClientSession`` (never closed by the library)
    or use the client as an async context manager to own one.
    """

    def __init__(
        self,
        email: str,
        password: str,
        session: aiohttp.ClientSession | None = None,
        *,
        base_url: str = API_BASE_URL,
    ) -> None:
        self._transport: CloudTransport | None = CloudTransport(email, password, session, base_url)
        self._requester: Requester = self._transport

    @classmethod
    def from_requester(cls, requester: Requester) -> Self:
        """Build a client over any ``Requester`` (tests, alternative transports)."""
        client = cls.__new__(cls)
        client._transport = None  # noqa: SLF001
        client._requester = requester  # noqa: SLF001
        return client

    def __repr__(self) -> str:
        return f"AirseekersCloud({self._transport!r})"

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the HTTP session if the client created it."""
        if self._transport is not None:
            await self._transport.close()

    @property
    def base_url(self) -> str | None:
        """Regional API host in use (switches after login, D7)."""
        return self._transport.base_url if self._transport else None

    def set_credentials(self, email: str, password: str) -> None:
        """Replace rejected credentials and clear the terminal auth state."""
        if self._transport is not None:
            self._transport.set_credentials(email, password)

    async def login(self) -> None:
        """Log in now instead of on the first call.

        Raises:
            AirseekersAuthError: the credentials were rejected (terminal).
        """
        if self._transport is not None:
            await self._transport.login()

    async def get_server_host(self) -> str:
        """Look up the regional API host and switch to it."""
        if self._transport is None:
            raise AirseekersApiError("no HTTP transport")
        return await self._transport.get_server_host()

    async def _get(self, path: str, sn: str, *, empty_codes: Sequence[int] = (), **params: str | int) -> Json:
        return await self._requester.request("GET", path, params={"sn": sn, **params}, empty_codes=empty_codes)

    async def _post(self, path: str, sn: str, extra: Mapping[str, object] | None = None) -> None:
        await self._requester.request("POST", path, payload={"sn": sn, **(extra or {})})

    # Account

    async def is_authorized(self) -> bool:
        """Return True if the current token is accepted."""
        try:
            await self._requester.request("GET", API_IS_AUTHORIZED)
        except AirseekersApiError:
            return False
        return True

    async def get_iot_cert(self) -> IoTCert:
        """Return MQTT credentials for the cloud broker."""
        data = _obj(await self._requester.request("POST", API_IOT_CERT, payload={}))
        try:
            return IoTCert(
                ca=str(data["ca"]),
                cert_key=str(data["cert_key"]),
                mqtt_broker=str(data["mqtt_broker"]),
                mqtt_client_id=str(data["mqtt_client_id"]),
                private_key=str(data["private_key"]),
            )
        except KeyError as err:
            raise AirseekersApiError(f"iot-cert response is missing {err}", path=API_IOT_CERT) from None

    async def get_devices(self) -> list[JsonObject]:
        """Return the devices bound to the account."""
        return _list(_obj(await self._requester.request("GET", API_DEVICES)).get("list"))

    async def bind_device(self, device_id: str) -> None:
        """Bind a device to the account."""
        await self._requester.request("POST", API_DEVICE_BIND, payload={"device_id": device_id})

    async def unbind_device(self, device_id: str) -> None:
        """Unbind a device from the account."""
        await self._requester.request("POST", API_DEVICE_UNBIND, payload={"device_id": device_id})

    # Device state

    async def get_full_status(self, sn: str) -> JsonObject:
        """Return the full device status (see ``docs/api/cloud.md`` for its sections)."""
        return _obj(await self._get(API_FULL_STATUS, sn))

    async def get_device_config(self, sn: str) -> dict[str, str]:
        """Return cloud-stored config keys (``SetVolume``, ``SetDarkMode``, ...)."""
        configs = _obj(await self._get(API_CONFIG, sn)).get("configs")
        return {str(k): str(v) for k, v in configs.items()} if isinstance(configs, dict) else {}

    async def get_device_map(self, sn: str) -> list[JsonObject]:
        """Return the device maps, each with GeoJSON ``geoData``."""
        return _list(await self._get(API_DEVICE_MAP, sn))

    async def get_device_map_v2(self, sn: str) -> JsonObject:
        """Return the v2 device-map payload.

        Observed in app v1.7.8 (GET, ``sn``); the response shape is not yet
        verified, so the raw mapping is returned (Q13).
        """
        return _obj(await self._get(API_DEVICE_MAP_V2, sn))

    async def get_map_geo_data(self, sn: str, map_id: str) -> JsonObject:
        """Return a single map's GeoJSON ``geoData`` by ``map_id``.

        Observed in app v1.7.8 (GET, ``sn`` + ``map_id``); response shape not
        yet verified, so the raw mapping is returned.
        """
        return _obj(await self._get(API_MAP_GEO_DATA, sn, map_id=map_id))

    async def get_explore_map_latest(self, sn: str) -> JsonObject:
        """Return the latest exploration-mapping result.

        Observed in app v1.7.8 (GET, ``sn``); response shape not yet verified.
        """
        return _obj(await self._get(API_EXPLORE_MAP_LATEST, sn))

    async def get_notifications(self, sn: str, page: int = 1, size: int = 10) -> list[JsonObject]:
        """Return device notifications, newest first."""
        return _list(_obj(await self._get(API_NOTIFY_LIST, sn, page=page, size=size)).get("list"))

    async def get_rtk_info(self, sn: str) -> JsonObject:
        """Return RTK base address info."""
        return _obj(await self._get(API_RTK_INFO, sn))

    async def get_warranty(self, sn: str) -> JsonObject:
        """Return warranty start/end epochs."""
        return _obj(await self._get(API_WARRANTY, sn))

    async def get_extended_warranty(self, sn: str) -> JsonObject:
        """Return extended warranty info, or ``{}`` if none was purchased."""
        return _obj(await self._get(API_EXTENDED_WARRANTY, sn, empty_codes=(CODE_NO_EXTENDED_WARRANTY,)))

    async def get_nrtk_supported(self, sn: str) -> JsonObject:
        """Return whether network RTK is available at the device location."""
        return _obj(await self._get(API_NRTK_SUPPORTED, sn))

    async def get_maintenance_list(self, sn: str) -> JsonObject:
        """Return the device maintenance items/reminders.

        Observed in app v1.7.8 (GET, ``sn``); response shape not yet verified.
        """
        return _obj(await self._get(API_MAINTENANCE_LIST, sn))

    async def get_sim_activation_status(self, sn: str) -> JsonObject:
        """Return the 4G SIM activation status.

        Observed in app v1.7.8 (GET, ``sn``); response shape not yet verified.
        """
        return _obj(await self._get(API_SIM_ACTIVATION_STATUS, sn))

    async def get_sim_package_info(self, sn: str) -> JsonObject:
        """Return the 4G SIM data-package info.

        Observed in app v1.7.8 (GET, ``sn``); response shape not yet verified.
        """
        return _obj(await self._get(API_SIM_PACKAGE_INFO, sn))

    async def get_voice_version(self, sn: str) -> JsonObject:
        """Return voice pack versions (current, new, upgradable)."""
        return _obj(await self._get(API_VOICE_VERSION, sn))

    async def get_firmware_latest(self, sn: str) -> JsonObject:
        """Return firmware metadata (``version``, ``current_version``, ``upgradable``)."""
        return _obj(await self._get(API_FIRMWARE_LATEST, sn, empty_codes=(CODE_ALREADY_LATEST,)))

    # Tasks

    async def get_device_tasks(self, sn: str) -> list[JsonObject]:
        """Return scheduled tasks."""
        return _list(_obj(await self._get(API_TASK, sn)).get("list"))

    async def get_latest_task(self, sn: str) -> JsonObject:
        """Return the most recently executed task definition (the app's Quick Mow)."""
        return _obj(await self._get(API_TASK_LATEST, sn))

    async def get_task_history(self, sn: str, page: int = 1, size: int = 10) -> JsonObject:
        """Return task records plus a ``summary`` of totals."""
        return _obj(await self._get(API_TASK_RECORD_LIST, sn, page=page, size=size))

    async def get_task_record_latest(self, sn: str) -> JsonObject:
        """Return the most recent completed task record."""
        return _obj(await self._get(API_TASK_RECORD_LATEST, sn))

    async def start_task(
        self,
        sn: str,
        *,
        task_id: str | None = None,
        map_id: str | None = None,
        mode: int | None = None,
        task_units: Sequence[Mapping[str, object]] | None = None,
    ) -> None:
        """Start a mowing task.

        The cloud needs the full task context; without ``task_units`` it
        answers -107 "operation not allowed". Omit ``task_id`` to run an
        ad-hoc task built from ``task_units`` (the app's Quick Mow).
        """
        extra: JsonObject = {}
        if task_id:
            extra["task_id"] = task_id
        if map_id:
            extra["map_id"] = map_id
        if mode is not None:
            extra["mode"] = mode
        if task_units:
            extra["task_units"] = [dict(unit) for unit in task_units]
        await self._post(API_TASK_START, sn, extra)

    async def stop_task(self, sn: str) -> None:
        """Stop the current task."""
        await self._post(API_TASK_STOP, sn)

    async def pause_task(self, sn: str) -> None:
        """Pause the current task."""
        await self._post(API_TASK_PAUSE, sn)

    async def resume_task(self, sn: str) -> None:
        """Resume a task paused in this session.

        Silently does nothing for a legacy task (robot docked mid-task);
        restart those with ``start_task(task_id=<legacy_task_id>, ...)``.
        """
        await self._post(API_TASK_RESUME, sn)

    async def dock(self, sn: str) -> None:
        """Return to the dock."""
        await self._post(API_TASK_DOCK, sn)

    async def update_task_cut_height(self, task: Mapping[str, object], height_mm: int) -> None:
        """Save ``cutter_height`` on every task unit of a scheduled task, without starting it."""
        height = max(CUT_HEIGHT_MIN_MM, min(CUT_HEIGHT_MAX_MM, height_mm))
        units = task.get("task_units")
        payload = dict(task)
        payload["task_units"] = [
            {**unit, "cutter_height": height}
            for unit in (units if isinstance(units, list) else [])
            if isinstance(unit, dict)
        ]
        await self._requester.request("PUT", API_TASK, payload=payload)

    # Settings

    async def set_config(self, sn: str, key: str, value: str) -> None:
        """Set a cloud config key.

        A flat ``{"sn", key: value}`` body is acknowledged but silently
        dropped; only the wrapped ``configs`` form persists (D8).
        """
        await self._post(API_CONFIG, sn, {"configs": {key: value}})

    async def set_volume(self, sn: str, volume: int) -> None:
        """Set the robot volume, 0-100."""
        await self.set_config(sn, "SetVolume", str(max(0, min(100, volume))))

    async def set_night_mode(self, sn: str, schedule: str) -> None:
        """Set night mode as ``"HH:MM-HH:MM"``; an empty string turns it off."""
        await self.set_config(sn, "SetDarkMode", schedule)

    async def set_fill_light(self, sn: str, brightness: int, *, enabled: bool) -> None:
        """Push the fill-light state to the robot now (code 309 if it is offline)."""
        await self._post(API_FILL_LIGHT, sn, {"lightBrightness": brightness, "fillLightSwitch": enabled})

    async def set_light_brightness(self, sn: str, brightness: int) -> None:
        """Set light brightness 0-100 in both the cloud config and on the robot, as the app does."""
        brightness = max(0, min(100, brightness))
        await self.set_config(sn, "SetLightBrightness", str(brightness))
        await self.set_fill_light(sn, brightness, enabled=brightness > 0)

    async def switch_map(self, sn: str, map_id: str) -> None:
        """Switch the active map."""
        await self._post(API_MAP_SWITCH, sn, {"map_id": map_id})

    # Maintenance

    async def rtk_reboot(self, sn: str) -> None:
        """Reboot the RTK base station."""
        await self._post(API_RTK_REBOOT, sn)

    async def clean_warnings(self, sn: str) -> None:
        """Clear warnings on the device."""
        await self._post(API_CLEAN_WARN, sn)

    async def lock(self, sn: str, password: str) -> None:
        """Lock the device (anti-theft)."""
        await self._post(API_DEVICE_LOCK, sn, {"password": password})

    async def unlock(self, sn: str, password: str) -> None:
        """Unlock the device."""
        await self._post(API_DEVICE_UNLOCK, sn, {"password": password})

    async def upgrade_firmware(self, sn: str) -> None:
        """Start a firmware upgrade."""
        await self._post(API_FIRMWARE_UPGRADE, sn)

    # Live video

    async def open_live_stream(self, sn: str, camera: int) -> str:
        """Return a short-lived WHEP URL for a camera: 1 front, 2 left, 3 right.

        The URL carries a signed ``secret`` valid for minutes, so fetch one
        per viewing session and never log it. Play it with
        ``pyairseekers.live.whep_play``.
        """
        url = _obj(await self._requester.request("POST", API_LIVE_OPEN, payload={"sn": sn, "camera": camera})).get(
            "url"
        )
        if not isinstance(url, str) or not url:
            raise AirseekersApiError("live/open returned no url", path=API_LIVE_OPEN)
        return url

    async def live_heartbeat(self, sn: str, camera: int) -> None:
        """Keep a camera stream alive.

        The cloud stops the stream unless the viewer calls this regularly
        (every ``const.LIVE_HEARTBEAT_INTERVAL_S``). The library never
        schedules it; the host does, for as long as someone is watching.
        """
        await self._post(API_LIVE_HEARTBEAT, sn, {"camera": camera})

    async def get_camera_params(self, sn: str) -> JsonObject:
        """Return live camera parameters.

        Observed in app v1.7.8 (GET, ``sn``); response shape not yet verified,
        so the raw mapping is returned.
        """
        return _obj(await self._get(API_LIVE_CAMERA_PARAMS, sn))

    async def move_control(self, sn: str, *, linear_x: float, angular_z: float) -> None:
        """Send one teleop velocity command: ``linear_x`` forward, ``angular_z`` yaw.

        This MOVES THE MOWER (cloud teleop; D14). It sends a single command and
        returns; it does not loop. ``linear_x`` and ``angular_z`` are normalized
        to about ``[-1.0, 1.0]`` (the app sends ``joystick_int * 0.01`` with the
        joystick clamped to ~±100; magnitudes below ~0.10 are a deadzone). Not
        m/s or rad/s. Ranges are observed from app v1.7.8 decompile, not yet
        verified on a Tron (Q14).

        Teleop needs a repeating stream and a stop; that is the caller's job, as
        with ``live_heartbeat``. The app re-sends at least every ~250 ms while
        moving, and to STOP sends ``(0, 0)`` twice about 50 ms apart.
        """
        await self._post(API_LIVE_MOVE_CONTROL, sn, {"linear_x": linear_x, "angular_z": angular_z})
