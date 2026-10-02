# Local Foxglove bridge

Module `pyairseekers/local/`. The mower runs `ros-foxglove-bridge` (ROS1
Noetic) on `ws://<mower-ip>:8765`, subprotocol `foxglove.websocket.v1`, no
authentication. Read freely; command only what D15 and D17 allow. The same
host also serves the HTTP API below on port 13344.

## Protocol as used

- On connect the bridge sends `serverInfo` (`sessionId`, `capabilities`) and
  `advertise` with channels `{id, topic, encoding: "ros1", schemaName,
  schema}`; `schema` is the ROS1 `.msg` text, usually base64.
- `subscribe {"subscriptions": [{"id", "channelId"}]}`.
- Message frames are binary: `0x01`, `uint32` subscription id, `uint64`
  timestamp, ROS1-serialised payload. `Typestore` decodes them from the
  advertised schema at runtime, so vendor `mower_msgs/*` types need no
  shipped definitions.

## Services

The bridge advertises `capabilities: ["services", ...]` and sends
`advertiseServices` after the channel advertisement: `{id, name, type,
requestSchema, responseSchema}` (newer bridges nest the schemas under
`request` / `response`). A call is binary: `0x02`, `uint32` service id,
`uint32` call id, `uint32` encoding length, `"ros1"`, ROS1-serialised request.
The answer is `0x03` with the same header and the response, or a JSON
`serviceCallFailure {serviceId, callId, message}`. Verified end to end on the
live bridge.

| Service | Type | Evidence | Library |
|---|---|---|---|
| `/controller/ctrl` | `mower_msgs/Trigger` | verified: req `string arg` ∈ `stop`/`pause`/`resume`; resp `int32 result` (0 ok, non-zero rejected or no-op, e.g. nothing to stop), `string message`; safe-stop verified on hardware; `resume` not yet exercised (Q16) | `MowerController.stop/pause` (D15) |
| `/controller/dock/ctrl` | `mower_msgs/Trigger` | schema verified, arguments unknown | not wrapped |
| `/controller/CheckStatus` | `mower_msgs/Trigger` | schema verified | not wrapped |
| `/cutter_control`, `/logic/cutter_control` | `mower_msgs/CutterControl` | schema verified: `MotorControl cutter`, `MotorControl height` (`bool enable, bool direction, int32 speed, int8 position`) → `bool result`; not exercised | not wrapped |

Topic publishing (`/cmd_vel`) is not implemented: it bypasses the mower's
control logic and its watchdog is unverified.

## HTTP API (`mower_logic`, port 13344)

`LocalApi(host, session)`. No authentication; listens on every interface.
Every response is an envelope `{"successed": bool, "errorCode": int, "msg":
str, "data": ...}`; `successed` false or a non-zero `errorCode` raises
`AirseekersApiError(code=errorCode)`.

| Method | Path | Library | Evidence |
|---|---|---|---|
| GET | `/map/list` | `map_list()` | verified: `[{mapId, mapName, createTime, geoData}]`, `geoData` in the local frame (metres from the dock; `properties.type` 1 work area, 3 channel, 4 no-go, 5 dock zone, 6 charge point, 7 undock point, 8 RTK base) |
| GET | `/task/getCoveragePath` | `coverage_path()` | observed (vendor spec) |
| GET | `/task/getWalkPath?point_index=` | `walk_path(i)` | observed (vendor spec) |
| POST | `/task/start` `{mapName}` | `start_task(name)` | observed (vendor spec); used per D17 |
| GET | `/task/pause` `/task/resume` `/task/stop` | `pause_task()` `resume_task()` `stop_task()` | observed (vendor spec); used per D17 |
| GET | `/task/dock` `/task/unDock` | `dock()` `undock()` | observed (vendor spec); used per D17 |
| GET | `/robot/task/info` | not wrapped | WebSocket task feed (spec): `startTime`, `state` idle/running/paused, `taskName` |
| POST/GET | `/map/save`, `/map/delete`, `/maping/*` | **not wrapped** | `/map/save` repointed the active map in testing (D17) |

## Topics read by the Home Assistant integration (verified)

| Topic | Type | Carries |
|---|---|---|
| `/battery` | `sensor_msgs/BatteryState` | percentage, voltage, current, temperature |
| `/fix` | `sensor_msgs/NavSatFix` | latitude, longitude, altitude, status |
| `/mower_base/status` | `mower_msgs/MowerBaseDevStatus` | charging, cutting, moving, docked, rain, lift, bumper, e-stop |
| `/mower_gps_node/info` | `mower_gps_msgs/Info` | satellites, quality, SNR, NRTK |
| `/mower_localization_info` | `mower_msgs/MowerLocalizationInfo` | RTK fix type, LoRa RSSI |
| `/task_info` | `std_msgs/String` (JSON) | `state`, `type`, `runTime`, areas, `params[].areaId` |
| `/geojson_task` | `foxglove_msgs/GeoJSON` | zones |
| `/mower_base/net_status` | `std_msgs/String` (JSON) | Wi-Fi RSSI |
| `/alarm_status`, `/notice_code`, `/notice_info`, `/controller/event`, `/robot_config`, `/task_report`, `/mower_sensor_info`, `/mower_base/{battery_health,dev_base_info,motor_info}` | various | raw |

Cameras are also published locally (`/{left_oa,right_oa,rear}_camera/image_raw`,
`/vio/*/image_raw/compressed`); turning streaming on is a publish
(`/mower_base/set_streaming`) and therefore out of scope (D15).
