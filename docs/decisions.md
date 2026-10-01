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
