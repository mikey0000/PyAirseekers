# Open questions

Things the evidence does not settle. Each has the conservative reading the
code takes today and what would close it. Closed questions are deleted and
their answer lands in `decisions.md` or `docs/api/`.

## Q3. What does a login failure look like?

Only "wrong password" is known to be non-zero. Today: any non-success login is
treated as a rejection and is terminal (D5), so a transient server-side
failure would also need `set_credentials`. Closes with captures of a wrong
password, an unknown email and a locked account.

## Q4. Which app headers does the server require?

The app (1.7.8, captured 2026-10-02) sends `accept-language`, `app-version`
(`1.7.8(2026092001)`), `content-type`, `country-code` (ISO country),
`user-agent: Dart/3.11 (dart:io)`, `x-app-device-model`, `x-app-device-os`,
`x-app-device-uuid` (per install) and `x-app-request-time` (unix seconds).
Today: we send `accept-language`, `app-version` and `content-type` only, and
deliberately do not imitate a device. Closes by calling each endpoint without
the extra headers; if `x-app-request-time` turns out to be checked, add it
(it is not an identity).

## Q5. Which read endpoints answer "empty" with a non-zero code?

Known: 407 on firmware/latest, 701 on extended-warranty. Others (task-record
on a new device, map on an unmapped device) may do the same. Today: raise.
Closes by exercising each read on a freshly bound device.

## Q6. The refresh-token grant

`/api/web/user/refresh-token` with `{"refresh_token"}` comes from app
analysis and has never been seen to succeed. Today: tried once on a stale
token, then password login. Closes with a capture.

## Q7. Token lifetime and proactive renewal

The access token is an HS256 JWT `{email, exp, sub}`. In the 2026-10-02
capture `exp` was about 2 h after the requests (issue time not seen), so the
original 23 h assumption was wrong. Today: renew reactively on an auth
failure (D5). Open: whether to renew ahead of `exp` instead, which would save
one failed request every couple of hours.

## Q8. Lock / unlock body

The two sources disagree: `{"sn", "password"}` versus `{"device_id"}`.
Today: `{"sn", "password"}`, unverified. Same doubt for bind, unbind and
firmware upgrade (`device_id` versus `sn`).

## Q9. Regional hosts

Does the login `host` always carry a scheme, and what do non-EU accounts get?
Today: switch only to an absolute `http(s)` URL.

## Q10. MQTT topics — mostly resolved

Resolved from app v1.7.8 decompile (see `docs/api/mqtt.md`): topics are
`common/app/{mqtt_client_id}/{sn}/be/up` (uplink) and `.../be/down` (downlink,
subscribed with `+` for `sn`); payload is a binary `Msg` protobuf keyed by the
(recovered) `MsgType` enum; MQTT v5 over mutual TLS, keepAlive 5 s, subscribe
QoS 1. Still open: broker host/port and cert material are runtime-only (from the
`iot-cert` bundle, not in the binary), protobuf field names are stripped, and
publish QoS/retain are inferred defaults. Closes fully with a broker capture.

## Q12. Heartbeat interval

Two app heartbeats were captured 38 s apart (`x-app-request-time`
1790894131 → 1790894169), both with the 36-byte `{sn, camera}` body. Today:
`LIVE_HEARTBEAT_INTERVAL_S = 20`, inside that gap even if the two were not
consecutive. Closes with a longer capture (several beats in a row) and the
time a stream survives without one.

## Q13. Observed read-only endpoint shapes

Seven read-only GET endpoints were added from app v1.7.8 decompile (method and
query params confirmed in `network/http_client.dart`): `device/map/v2`,
`device/map/geo-data` (`sn`+`map_id`), `device/explore-map/latest`,
`device/maintenance/list`, `device/sim/activation-status`,
`device/sim/package-info`, `live/camera-params` — all GET with `sn`. Their
*response* bodies are not yet verified against a real Tron, so the wrappers
return the raw mapping. Closes with a capture of each response (promotes them
to verified in `docs/api/cloud.md`).

## Q14. Cloud teleop: ranges and stop-on-silence

`move_control` sends `{sn, linear_x, angular_z}`; the decompile suggests both
are normalised to about ±1.0 (joystick × 0.01, deadzone below ~0.10), resent
at least every ~250 ms, and stopped by sending `(0, 0)` twice ~50 ms apart.
Unknown: whether the robot (or the cloud) stops the mower when commands stop
arriving, and after how long. Today: one command per call; the host owns the
stream and the stop (D14); the Home Assistant integration does not use it.
Closes with an on-device test: drive briefly, stop sending without `(0, 0)`,
and time how long the mower keeps moving (from a safe distance, with the
local `/controller/ctrl stop` ready).

## Q15. How do local controller commands relate to the cloud task?

`/controller/ctrl` drives the low-level controller inside a task's behaviour
tree. Unknown: after a local `pause`, does cloud `full-status` report the task
as paused (`state == 2`), and does cloud `task/resume` undo it, or only local
`resume`? After a local `stop`, is the task ended or left as a legacy task?
Today: hosts should not mix a local pause with a cloud resume. Closes by
pausing locally and reading `full-status`, then resuming each way.

## Q16. Has `resume` been exercised on a mower?

The `/controller/ctrl` argument `resume` is known from the schema and from
the behaviour-tree callers, but only `stop` is recorded as tested on
hardware. Today: `MowerController` offers `stop` and `pause` only (D15).
Closes when `resume` is run on a Tron (after a local `pause`, with `stop`
ready) and its effect and `result` are recorded; then add the method.
