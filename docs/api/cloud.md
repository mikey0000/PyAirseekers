# Cloud REST

Module `pyairseekers/cloud/`. Paths are constants in `const.py`.

**Envelope.** Every response is `{"code", "data", "errorCode", "msg"}`.
Success is `code == 0`. A non-zero code raises `AirseekersApiError` unless it
is listed as an empty code below (D6). **Auth.** `Authorization: Bearer
<access_token>` (HS256 JWT `{email, exp, sub}`, about 2 h lifetime, Q7) plus
the app's `app-version` / `accept-language` headers. The app sends more
device headers that we do not (Q4).
Device calls identify the mower by serial number `sn`.

## Account

| Method | Call | Evidence | Notes |
|---|---|---|---|
| `POST /user/login` | `login()` (lazy) | verified | `{email, password}` → `{access_token, refresh_token, host, language}`; switches to `host` (D7); failure is terminal (D5, Q3) |
| `POST /api/web/user/refresh-token` | (internal) | observed | `{refresh_token}` → `{access_token}` (Q6) |
| `GET /api/web/server-host` | `get_server_host()` | observed | no auth; `{host}` |
| `GET /api/web/user/is-authorized` | `is_authorized()` | observed | |
| `POST /api/web/device/iot-cert` | `get_iot_cert() -> IoTCert` | observed | MQTT CA, cert, key, broker, client id (Q10) |
| `GET /api/web/device` | `get_devices()` | verified | `data.list[]`: `sn`, `online_status` (1 online), `ip`, `firmware_ver`, `lock_status`, `nrtk_info`, `func_list`, ... |
| `POST /api/web/device/bind` / `unbind` | `bind_device(id)` / `unbind_device(id)` | observed | body key `device_id` (Q8) |

## Device state (reads)

| Method | Call | Evidence | Notes |
|---|---|---|---|
| `GET /api/web/device/full-status?sn=` | `get_full_status(sn)` | verified | sections: `battery_status`, `task_status` (`state` 0 idle 1 running 2 paused; `is_has_legacy_task`, `legacy_task_id`, `map_id`), `rtk_status`, `rtk_info`, `net_info` (`wifi_ip`, `wifi_dbm`, `wireless_4g_ip`), `sensor_status`, `version`, `upgrade_status`, `upgrade_mcu_status`, `voice_upgrade_status`, `explore_mapping_info` |
| `GET /api/web/device/config?sn=` | `get_device_config(sn)` | verified | `data.configs`: string values; `SetVolume` 0-100, `SetLightBrightness` 0-100, `SetDarkMode` `"HH:MM-HH:MM"` or `""`, `DeviceLock`, `EnableNRTK`, `Net4GAllowUploadPicture` |
| `GET /api/web/device/map?sn=` | `get_device_map(sn)` | verified | list of maps with `mapId`, `geoData` (GeoJSON; `properties.type` 1 = mowable zone with `name`, `id`) |
| `GET /api/web/device/notify/list?sn=&page=&size=` | `get_notifications(sn)` | verified | `data.list[]` with `notify_class`, `notify_type`, `content`, `created_at` |
| `GET /api/web/device/rtk/address-info?sn=` | `get_rtk_info(sn)` | verified | |
| `GET /api/web/device/warranty/info?sn=` | `get_warranty(sn)` | verified | `start_at`, `end_at` |
| `GET /api/web/device/extended-warranty/info?sn=` | `get_extended_warranty(sn)` | verified | empty code **701** (not purchased) |
| `GET /api/web/device/nrtk-supported?sn=` | `get_nrtk_supported(sn)` | verified | `available` |
| `GET /api/web/voice-version/latest?sn=` | `get_voice_version(sn)` | verified | `current_version`, `new_version`, `upgradable`, `change_log` |
| `GET /api/web/firmware/latest?sn=` | `get_firmware_latest(sn)` | verified | empty code **407** (already latest; `data` still carries versions) |

## Tasks

| Method | Call | Evidence | Notes |
|---|---|---|---|
| `GET /api/web/device/task?sn=` | `get_device_tasks(sn)` | verified | `data.list[]` scheduled tasks: `id`, `map_id`, `mode`, `task_units[]` |
| `PUT /api/web/device/task` | `update_task_cut_height(task, mm)` | verified | the full task object back with every unit's `cutter_height` set; does not start |
| `GET /api/web/device/task/latest?sn=` | `get_latest_task(sn)` | verified | the last executed definition (Quick Mow) |
| `GET /api/web/device/task-record/list?sn=&page=&size=` | `get_task_history(sn)` | verified | records plus `summary` (`total_area`, `total_duration`, `total_count`) |
| `GET /api/web/device/task-record/latest?sn=` | `get_task_record_latest(sn)` | verified | |
| `POST /api/web/device/task/start` | `start_task(sn, task_id, map_id, mode, task_units)` | verified | without `task_units` → **-107**; omit `task_id` for an ad-hoc task |
| `POST /api/web/device/task/stop` | `stop_task(sn)` | verified | |
| `POST /api/web/device/task/pause` | `pause_task(sn)` | verified | |
| `POST /api/web/device/task/resume` | `resume_task(sn)` | verified | no-op for a legacy task: restart with `start_task(task_id=legacy_task_id)` |
| `POST /api/web/device/task/dock` | `dock(sn)` | verified | |

`mode`: 0 global, 1 AI, 2 edge, 3 area. Task unit fields: `areaId`,
`cut_mode` (1 mow, 0 skip; every zone must be present), `cutter_height` (mm;
app 30-90 step 10), `path_angle` (radians), `cut_speed` (1 slow, 2 normal,
3 fast), `strategy` (1 stability, 2 dense, 3 spare), `truning_mode` (sic;
1 fishtail, 2 circular, 3 turn in place). Lookups in `const.py`.

## Settings and maintenance

| Method | Call | Evidence | Notes |
|---|---|---|---|
| `POST /api/web/device/config` | `set_config`, `set_volume`, `set_night_mode` | verified | wrapped body `{sn, configs: {key: value}}` only (D8) |
| `POST /api/web/device/fill-light-setting` | `set_fill_light(sn, b, enabled=)`; `set_light_brightness` | verified | `{lightBrightness, fillLightSwitch}`; **309** if offline |
| `POST /api/web/device/map/switch` | `switch_map(sn, map_id)` | observed | |
| `POST /api/web/device/rtk-reboot` | `rtk_reboot(sn)` | observed | |
| `POST /api/web/device/clean-warn` | `clean_warnings(sn)` | observed | |
| `POST /api/web/device/lock` / `unlock` | `lock(sn, pw)` / `unlock(sn, pw)` | inferred | body uncertain (Q8) |
| `POST /api/web/firmware/upgrade` | `upgrade_firmware(sn)` | observed | body key uncertain (Q8) |

## Live video

| Method | Call | Evidence | Notes |
|---|---|---|---|
| `POST /api/web/live/heartbeat` | `live_heartbeat(sn, camera)` | observed | `{sn, camera}` → `data: null`; keeps the stream alive; app seen calling it 38 s apart; the host calls it every `LIVE_HEARTBEAT_INTERVAL_S` (20 s) while viewing (Q12) |
| `POST /api/web/live/open` | `open_live_stream(sn, camera) -> str` | verified | `{sn, camera}` (1 front, 2 left, 3 right) → `{url}`; see [live](live.md); the URL is a secret (D13) |

## Codes seen

| Code | Where | Meaning |
|---|---|---|
| 0 | everywhere | success |
| 309 | commands | device offline or busy |
| 407 | firmware/latest | already latest (empty) |
| 701 | extended-warranty | not purchased (empty) |
| -107 | task/start | operation not allowed (missing `task_units`) |
