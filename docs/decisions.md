# Decisions

Numbered, append-only. A decision is superseded by a later entry, never
edited away. Each entry states the choice and the reason; alternatives get one
line at most.

## D1. Evidence-graded, not clean-room

Airseekers publishes no API, so a clean-room build is impossible. The package
is assembled from app traffic, app analysis and two Home Assistant
integrations that exercised a real Tron, and every endpoint carries an
evidence level in `docs/api/` (verified / observed / inferred). Reason: the
reader must be able to tell a tested call from a guess before sending it to a
machine with blades.

## D2. One package, three independent transports

Cloud REST, local Foxglove and WHEP live video share a package (one
dependency for hosts) but not code paths: none imports another. Reason: they
fail independently (the cloud can be down while the LAN is fine, and the
reverse) and a host should be able to use any subset. The first host, the Home
Assistant integration, reads locally and writes through the cloud.

## D3. The local bridge stays read-only

`FoxgloveClient` subscribes; it never publishes or calls services. Reason:
the bridge exposes raw control (`/cmd_vel` bypasses the mower's own logic) and
neither the command schemas nor safe-stop have been verified on a device.
Superseding this requires the evidence listed in CONSTITUTION §2.
Superseded for `/controller/ctrl` `stop` and `pause` by D15.

## D4. Cloud responses are mappings until verified

Read methods return `dict`s narrowed with `isinstance`, not typed models.
Reason: most response shapes are known from a handful of captures; a typed
model would encode guesses as contracts and break on the first difference.
Shapes the library itself consumes (`IoTCert`) or builds (`LiveStream`) are
models. Pydantic (in the original package) was dropped: it was the only
non-aiohttp runtime dependency and validated nothing we had verified.

## D5. Lazy login, one renewal per stale token, terminal rejection

The first call logs in. On an auth failure the transport renews under a lock,
keyed on the token the caller sent, so a burst of failures produces one
renewal; it tries the refresh token, then the password. A rejected login sets
a terminal flag: later calls raise without I/O until `set_credentials()`.
Reason: repeated password attempts risk an account lockout and spam the
vendor; a host polling every few seconds would otherwise hammer the login
endpoint with a bad password. No scheduler: there is nothing to keep warm.

## D6. Non-success raises, except per-endpoint empty codes

Commands return `None` and raise `AirseekersApiError` on any non-success
code; reads do the same, except codes documented as "nothing here" on that
one endpoint (`407` firmware already latest, `701` no extended warranty),
passed as `empty_codes` at the call site. Reason: the integrations this grew
from returned `False` / `{}` for every failure, which hid offline devices
(`309`) and rejected starts (`-107`) behind empty data. Unknown "empty" codes
are Q5.

## D7. The login response chooses the host

Calls start at `API_BASE_URL` (EU) and switch to the `host` the login
response returns, when it is an absolute URL. Reason: the app does the same,
and non-EU accounts would otherwise talk to the wrong region. `get_server_host`
exists for hosts that want to look it up before login.

## D8. Config writes use the wrapped body

`set_config` sends `{"sn", "configs": {key: value}}`. Reason: the flat
`{"sn", key: value}` form is acknowledged with code 0 but silently dropped;
the wrapped form was verified by writing a unique value and reading it back.

## D9. MQTT and BLE are experimental

`mqtt.py` and `ble.py` predate any hardware access, use a thread-based MQTT
loop, and guess their topics. They stay importable (and in `[mqtt]`/`[ble]`
extras) but are excluded from ruff, ty, coverage and the mirroring rule, and
are not in `__all__`. Reason: holding them to the bar now would mean
inventing behaviour; deleting them would lose the cert and BLE UUID findings.
Promote by the recipe in `architecture.md` §4.

## D10. Live video is an SDP broker

`whep_play` posts the host's SDP offer and returns SRS's answer; the library
never touches media. Reason: the consumer (a browser, Home Assistant's WebRTC
stack) already has a WebRTC peer, SRS is ICE-lite with its candidates in the
answer, and pulling `aiortc` into the package would add a heavy native
dependency for no gain.

## D11. The cloud transport is tested over loopback

`CloudTransport` uses `aiohttp` directly and is tested against
`tests/integration/fakeserver/cloud.py`; only the API layer has a protocol
seam (`Requester`). Reason: there is one HTTP implementation, and an
`HttpSession` protocol would be ceremony; the fake server exercises real
status codes, bodies and headers, which a fake session would only imitate.

## D12. Hand-written fakes, no mocking library

See `docs/testing.md` §3. Reason: a `MagicMock` keeps passing after the
interface it stands for changes.

## D13. The live-stream URL is a secret

`open_live_stream` returns a URL whose `secret` query parameter is a signed
token that plays the camera. It is never logged, never put in an exception,
and `LiveStream` hides its resource URL from `repr`. Reason: anyone with the
URL can watch the camera until it expires.

## D14. Cloud teleop (`move-control`) is wrapped; local teleop is not

`move_control(sn, linear_x, angular_z)` posts `/api/web/live/move-control`
(body `{sn, linear_x, angular_z}`, confirmed from app v1.7.8 decompile). This
is a **cloud** motion command on the same footing as `start_task`/`dock`. It
does **not** touch the local bridge, so CONSTITUTION §2 is untouched. Whether
the robot stops by itself when commands stop arriving (a host that crashes
mid-move) is **unknown** (Q14); until that is answered hosts must not expose
`move_control` without their own stop-on-release handling, and the Home
Assistant integration does not wrap it. Evidence is `observed` until exercised
on a Tron (Q14). Reason/scope: the method does one thing — send one velocity command;
it does not loop. Teleop needs a repeating command stream and a stop; keeping
the device moving and stopping it are the host's responsibility, exactly like
`live_heartbeat`. The docstring says so.

## D15. Local controller commands: stop, pause, resume

Supersedes D3 for one service. The `mower_msgs/Trigger` schema behind
`/controller/ctrl` was read live from `advertiseServices` (request
`string arg`; response `int32 result`, `string message`), the arguments
`stop`, `pause` and `resume` were confirmed, and safe-stop (`stop`) was
verified on a Tron over the bridge (2026-10, recorded in
airseekers-tron-ha-local `docs/protocol-reference.md`). The service-call wire
path (`0x02` request / `0x03` response / `serviceCallFailure`) was verified
against the live bridge with a benign service.

So `FoxgloveClient` gains `call_service(service, request)` as a raw transport
primitive, public so verification scripts can use it, and
`local/control.py::MowerController` is the library's only caller. Each
command: refuses a bridge without the `services` capability; refuses if the
advertised request or response schema differs from the verified one (a
firmware change must not be driven blind); confirms the response and raises
`AirseekersServiceError` on a non-zero `result` or a `serviceCallFailure`;
raises `AirseekersTransportError` if no answer arrives within
`SERVICE_CALL_TIMEOUT`. Reason: a local stop works without the internet and
reaches the mower faster than the cloud.

`resume` is held back although the argument is known: it sets a bladed mower
moving, and only `stop` is recorded as exercised on hardware (Q16). Not
opened either: `publish` (and with it `/cmd_vel`, whose watchdog is unverified),
`/controller/dock/ctrl` (arguments unknown), `/cutter_control` (schema known,
not exercised), and every power service. `/controller/ctrl` is the low-level
controller inside a task's behaviour tree, not the task layer, so whether a
local `pause` is visible to the cloud's task state is Q15.

## D16. The Foxglove client owns its connection lifecycle

`connect()` tears down any previous connection first; the receive loop starts
in `connect()` (so service adverts and call responses are handled before
`subscribe`), survives a malformed frame by dropping it, and when it ends it
fails pending calls and closes the socket so `connected` turns False. The
connection callback reports unexpected loss only; `disconnect()` clears it
and forgets channels, schemas and services. Reason: the review of D15 found a
single bad frame ended the stream while `connected` stayed True, so Home
Assistant's reconnect loop never ran, and a second `connect()` left the old
loop failing the new connection's calls.
