from __future__ import annotations

import math

import pytest

from pyairseekers import AirseekersApiError, AirseekersCloud
from pyairseekers.const import (
    API_CONFIG,
    API_DEVICES,
    API_EXTENDED_WARRANTY,
    API_FILL_LIGHT,
    API_FIRMWARE_LATEST,
    API_IOT_CERT,
    API_LIVE_OPEN,
    API_TASK,
    API_TASK_DOCK,
    API_TASK_START,
    CODE_ALREADY_LATEST,
    CODE_NO_EXTENDED_WARRANTY,
)
from tests._helpers import EMAIL, PASSWORD, SN
from tests.unit._fakes import FakeRequester


@pytest.fixture
def requester() -> FakeRequester:
    return FakeRequester()


@pytest.fixture
def cloud(requester: FakeRequester) -> AirseekersCloud:
    return AirseekersCloud.from_requester(requester)


class TestReads:
    async def test_get_devices_returns_the_list(self, cloud: AirseekersCloud, requester: FakeRequester) -> None:
        requester.queue({"list": [{"sn": SN}, "not-a-device"], "total": 2})

        devices = await cloud.get_devices()

        assert devices == [{"sn": SN}]
        assert requester.last.path == API_DEVICES

    async def test_get_device_config_flattens_configs_to_strings(
        self, cloud: AirseekersCloud, requester: FakeRequester
    ) -> None:
        requester.queue({"configs": {"SetVolume": 40, "SetDarkMode": ""}})

        config = await cloud.get_device_config(SN)

        assert config == {"SetVolume": "40", "SetDarkMode": ""}
        assert requester.last.params == {"sn": SN}

    async def test_non_dict_data_reads_as_empty(self, cloud: AirseekersCloud, requester: FakeRequester) -> None:
        requester.queue(None)

        assert await cloud.get_full_status(SN) == {}

    async def test_read_raises_on_non_success_code(self, cloud: AirseekersCloud, requester: FakeRequester) -> None:
        requester.queue(AirseekersApiError("device offline", code=309))

        with pytest.raises(AirseekersApiError) as err:
            await cloud.get_full_status(SN)

        assert err.value.code == 309

    @pytest.mark.parametrize(
        ("method", "path", "code"),
        [
            ("get_firmware_latest", API_FIRMWARE_LATEST, CODE_ALREADY_LATEST),
            ("get_extended_warranty", API_EXTENDED_WARRANTY, CODE_NO_EXTENDED_WARRANTY),
        ],
    )
    async def test_documented_empty_code_reads_as_empty(
        self, cloud: AirseekersCloud, requester: FakeRequester, method: str, path: str, code: int
    ) -> None:
        requester.queue(AirseekersApiError("nothing", code=code))

        assert await getattr(cloud, method)(SN) == {}
        assert requester.last.path == path

    async def test_get_iot_cert_redacts_keys(self, cloud: AirseekersCloud, requester: FakeRequester) -> None:
        requester.queue(
            {
                "ca": "ca",
                "cert_key": "cert-secret",
                "mqtt_broker": "b:8883",
                "mqtt_client_id": "c",
                "private_key": "pk-secret",
            }
        )

        cert = await cloud.get_iot_cert()

        assert cert.private_key == "pk-secret"
        assert "pk-secret" not in repr(cert)
        assert "cert-secret" not in repr(cert)
        assert requester.last.path == API_IOT_CERT

    async def test_get_iot_cert_names_a_missing_field(self, cloud: AirseekersCloud, requester: FakeRequester) -> None:
        requester.queue({"ca": "ca"})

        with pytest.raises(AirseekersApiError, match="cert_key"):
            await cloud.get_iot_cert()


class TestCommands:
    async def test_dock_posts_the_serial(self, cloud: AirseekersCloud, requester: FakeRequester) -> None:
        await cloud.dock(SN)

        assert (requester.last.method, requester.last.path, requester.last.payload) == (
            "POST",
            API_TASK_DOCK,
            {"sn": SN},
        )

    async def test_rejected_command_raises(self, cloud: AirseekersCloud, requester: FakeRequester) -> None:
        requester.queue(AirseekersApiError("operation not allowed", code=-107))

        with pytest.raises(AirseekersApiError) as err:
            await cloud.dock(SN)

        assert err.value.code == -107

    async def test_start_task_sends_only_given_fields(self, cloud: AirseekersCloud, requester: FakeRequester) -> None:
        unit = {"areaId": "a1", "path_angle": math.pi}

        await cloud.start_task(SN, map_id="m1", mode=0, task_units=[unit])

        assert requester.last.path == API_TASK_START
        assert requester.last.payload == {"sn": SN, "map_id": "m1", "mode": 0, "task_units": [unit]}

    async def test_set_config_uses_the_wrapped_body(self, cloud: AirseekersCloud, requester: FakeRequester) -> None:
        await cloud.set_volume(SN, 150)

        assert requester.last.path == API_CONFIG
        assert requester.last.payload == {"sn": SN, "configs": {"SetVolume": "100"}}

    async def test_set_light_brightness_writes_config_then_pushes_to_robot(
        self, cloud: AirseekersCloud, requester: FakeRequester
    ) -> None:
        await cloud.set_light_brightness(SN, 0)

        assert [c.path for c in requester.calls] == [API_CONFIG, API_FILL_LIGHT]
        assert requester.last.payload == {"sn": SN, "lightBrightness": 0, "fillLightSwitch": False}

    async def test_update_task_cut_height_clamps_and_keeps_other_fields(
        self, cloud: AirseekersCloud, requester: FakeRequester
    ) -> None:
        task = {"id": "t1", "task_units": [{"areaId": "a1", "cutter_height": 50}]}

        await cloud.update_task_cut_height(task, 500)

        assert (requester.last.method, requester.last.path) == ("PUT", API_TASK)
        assert requester.last.payload == {"id": "t1", "task_units": [{"areaId": "a1", "cutter_height": 120}]}
        assert task["task_units"] == [{"areaId": "a1", "cutter_height": 50}]


class TestLiveStream:
    async def test_open_live_stream_returns_the_url(self, cloud: AirseekersCloud, requester: FakeRequester) -> None:
        requester.queue({"url": "http://srs.invalid/rtc/v1/whep/?stream=x"})

        url = await cloud.open_live_stream(SN, 3)

        assert url.startswith("http://srs.invalid/")
        assert requester.last.path == API_LIVE_OPEN
        assert requester.last.payload == {"sn": SN, "camera": 3}

    async def test_open_live_stream_without_url_raises(self, cloud: AirseekersCloud, requester: FakeRequester) -> None:
        requester.queue({})

        with pytest.raises(AirseekersApiError, match="no url"):
            await cloud.open_live_stream(SN, 1)


class TestRepr:
    def test_repr_does_not_contain_credentials(self) -> None:
        cloud = AirseekersCloud(EMAIL, PASSWORD)

        assert PASSWORD not in repr(cloud)
        assert EMAIL not in repr(cloud)


class TestEndpointTable:
    """Every endpoint wrapper sends the documented method, path and body (docs/api/cloud.md)."""

    @pytest.mark.parametrize(
        ("call", "method", "path", "params", "payload"),
        [
            (lambda c: c.get_full_status(SN), "GET", "/api/web/device/full-status", {"sn": SN}, None),
            (lambda c: c.get_device_map(SN), "GET", "/api/web/device/map", {"sn": SN}, None),
            (lambda c: c.get_device_tasks(SN), "GET", "/api/web/device/task", {"sn": SN}, None),
            (lambda c: c.get_latest_task(SN), "GET", "/api/web/device/task/latest", {"sn": SN}, None),
            (
                lambda c: c.get_task_history(SN, page=2, size=5),
                "GET",
                "/api/web/device/task-record/list",
                {"sn": SN, "page": 2, "size": 5},
                None,
            ),
            (lambda c: c.get_task_record_latest(SN), "GET", "/api/web/device/task-record/latest", {"sn": SN}, None),
            (
                lambda c: c.get_notifications(SN),
                "GET",
                "/api/web/device/notify/list",
                {"sn": SN, "page": 1, "size": 10},
                None,
            ),
            (lambda c: c.get_rtk_info(SN), "GET", "/api/web/device/rtk/address-info", {"sn": SN}, None),
            (lambda c: c.get_warranty(SN), "GET", "/api/web/device/warranty/info", {"sn": SN}, None),
            (lambda c: c.get_nrtk_supported(SN), "GET", "/api/web/device/nrtk-supported", {"sn": SN}, None),
            (lambda c: c.get_voice_version(SN), "GET", "/api/web/voice-version/latest", {"sn": SN}, None),
            (lambda c: c.get_device_map_v2(SN), "GET", "/api/web/device/map/v2", {"sn": SN}, None),
            (
                lambda c: c.get_map_geo_data(SN, "m1"),
                "GET",
                "/api/web/device/map/geo-data",
                {"sn": SN, "map_id": "m1"},
                None,
            ),
            (lambda c: c.get_explore_map_latest(SN), "GET", "/api/web/device/explore-map/latest", {"sn": SN}, None),
            (lambda c: c.get_maintenance_list(SN), "GET", "/api/web/device/maintenance/list", {"sn": SN}, None),
            (
                lambda c: c.get_sim_activation_status(SN),
                "GET",
                "/api/web/device/sim/activation-status",
                {"sn": SN},
                None,
            ),
            (lambda c: c.get_sim_package_info(SN), "GET", "/api/web/device/sim/package-info", {"sn": SN}, None),
            (lambda c: c.get_camera_params(SN), "GET", "/api/web/live/camera-params", {"sn": SN}, None),
            (lambda c: c.stop_task(SN), "POST", "/api/web/device/task/stop", None, {"sn": SN}),
            (lambda c: c.pause_task(SN), "POST", "/api/web/device/task/pause", None, {"sn": SN}),
            (lambda c: c.resume_task(SN), "POST", "/api/web/device/task/resume", None, {"sn": SN}),
            (lambda c: c.rtk_reboot(SN), "POST", "/api/web/device/rtk-reboot", None, {"sn": SN}),
            (lambda c: c.clean_warnings(SN), "POST", "/api/web/device/clean-warn", None, {"sn": SN}),
            (lambda c: c.upgrade_firmware(SN), "POST", "/api/web/firmware/upgrade", None, {"sn": SN}),
            (
                lambda c: c.switch_map(SN, "m2"),
                "POST",
                "/api/web/device/map/switch",
                None,
                {"sn": SN, "map_id": "m2"},
            ),
            (
                lambda c: c.set_night_mode(SN, "22:00-06:00"),
                "POST",
                "/api/web/device/config",
                None,
                {"sn": SN, "configs": {"SetDarkMode": "22:00-06:00"}},
            ),
            (lambda c: c.lock(SN, "1234"), "POST", "/api/web/device/lock", None, {"sn": SN, "password": "1234"}),
            (lambda c: c.unlock(SN, "1234"), "POST", "/api/web/device/unlock", None, {"sn": SN, "password": "1234"}),
            (lambda c: c.bind_device("d1"), "POST", "/api/web/device/bind", None, {"device_id": "d1"}),
            (lambda c: c.unbind_device("d1"), "POST", "/api/web/device/unbind", None, {"device_id": "d1"}),
            (
                lambda c: c.live_heartbeat(SN, 3),
                "POST",
                "/api/web/live/heartbeat",
                None,
                {"sn": SN, "camera": 3},
            ),
            (
                lambda c: c.move_control(SN, linear_x=0.5, angular_z=-0.2),
                "POST",
                "/api/web/live/move-control",
                None,
                {"sn": SN, "linear_x": 0.5, "angular_z": -0.2},
            ),
        ],
    )
    async def test_request_shape(
        self,
        cloud: AirseekersCloud,
        requester: FakeRequester,
        call: object,
        method: str,
        path: str,
        params: dict[str, object] | None,
        payload: dict[str, object] | None,
    ) -> None:
        await call(cloud)  # type: ignore[operator]

        assert (requester.last.method, requester.last.path) == (method, path)
        assert requester.last.params == params
        assert requester.last.payload == payload

    async def test_is_authorized_is_false_on_rejection(self, cloud: AirseekersCloud, requester: FakeRequester) -> None:
        requester.queue(AirseekersApiError("no", code=401))

        assert await cloud.is_authorized() is False
