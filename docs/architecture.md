# Architecture

`pyairseekers` is an asynchronous Python client for the Airseekers Tron. It
wraps three independent transports and adds only the credential and error
handling the vendor leaves to the client. This document is the map. The rules
are in `CONSTITUTION.md`; the reasons are in `decisions.md`.

## 1. Layer map

```
┌──────────────────────────────────────────────────────────────┐
│ cloud/api.py — AirseekersCloud                                │
│   One method per endpoint. Builds path + body, calls the      │
│   Requester, shapes data into a mapping or a model.           │
│   Async context manager; from_requester() for tests.          │
├──────────────────────────────────────────────────────────────┤
│ cloud/transport.py — CloudTransport (implements Requester)    │
│   Login, refresh, token lock, terminal rejection, HTTP,       │
│   envelope → data or exception, the single renewal retry.     │
├──────────────────────────────────────────────────────────────┤
│ live.py — whep_play / whep_stop                               │
│   SDP offer → SRS → SDP answer. No media handling (D10).      │
├──────────────────────────────────────────────────────────────┤
│ local/foxglove.py — FoxgloveClient                            │
│   foxglove.websocket.v1: serverInfo, advertise, subscribe,    │
│   binary message frames → decoded ROS1 objects. Read-only.    │
│ local/ros1.py — Typestore, parse_msg_text, to_type_path       │
│   Registers ROS1 .msg schemas at runtime; decodes payloads.   │
├──────────────────────────────────────────────────────────────┤
│ models.py      IoTCert, LiveStream, BLEDevice (redacting)     │
│ exceptions.py  the whole hierarchy; nothing raised elsewhere  │
│ const.py       base URL, timeouts, wire codes, paths, enums   │
├──────────────────────────────────────────────────────────────┤
│ mqtt.py, ble.py — experimental (D9), outside the bar          │
└──────────────────────────────────────────────────────────────┘
```

`cloud`, `live` and `local` never import each other. `cloud/api.py` talks to
the `Requester` protocol and constructs `CloudTransport` only as its default.
`local` imports only `exceptions`. `tests/meta/test_conventions.py` asserts
this map (`ALLOWED_IMPORTS`).

A host composes the transports. The Home Assistant integration reads from
`FoxgloveClient`, writes through `AirseekersCloud`, and plays video with
`open_live_stream` + `whep_play`.

## 2. The flows

### 2.1 A cloud request

```
AirseekersCloud.dock(sn)
  → Requester.request("POST", "/api/web/device/task/dock", payload={"sn": sn})
      1. token = _token()             terminal flag → AirseekersAuthError, no I/O
      2. HTTP with Bearer token, app headers, REQUEST_TIMEOUT_S
      3. 408/429/5xx, network, timeout   → AirseekersTransportError
         non-JSON 4xx                     → AirseekersApiError(code=status)
         non-JSON 2xx/3xx                 → AirseekersTransportError
      4. auth failure (401, or a non-success envelope whose msg names a
         token/credential) → _token(stale=token); retry once; a second auth
         failure raises AirseekersApiError
      5. envelope code ≠ 0 and not in this call's empty_codes
                                          → AirseekersApiError(code, path)
      6. return envelope["data"]
  → command methods return None; read methods shape data into a mapping
```

### 2.2 A token

```
CloudTransport._token(stale=None)
  ├─ rejected flag set                  → AirseekersAuthError (no I/O)
  ├─ have a token that is not `stale`   → return it
  └─ under asyncio.Lock:
       re-check (another caller may have renewed while we waited)
       stale and refresh token held → POST refresh-token
           rejected                 → fall through
       POST /user/login
           rejected                 → set rejected flag, AirseekersAuthError
           accepted                 → store tokens, switch base_url to `host` (D7)
       AirseekersTransportError at any step → propagate; state untouched
```

Login is lazy: the first call logs in. There is no scheduler (D5).

### 2.3 Live video

```
host: url = await cloud.open_live_stream(sn, camera)   # POST /api/web/live/open
host: stream = await whep_play(session, url, offer)     # POST offer → 201 answer + Location
host: hands stream.answer_sdp to its WebRTC peer (browser); media flows peer ↔ SRS
host: await whep_stop(session, stream)                  # DELETE Location
```

### 2.4 Local telemetry

```
FoxgloveClient.connect()     ws://<ip>:8765, subprotocol foxglove.websocket.v1
  ← serverInfo, advertise(channels with base64 ROS1 schemas)
FoxgloveClient.subscribe(topics, on_message, on_connection)
  → registers each schema with Typestore, sends subscribe, starts receive loop
  ← binary 0x01 frames → Typestore.deserialize_ros1 → on_message(topic, schema, obj)
  loop ends (close/error) → on_connection(False); reconnecting is the host's job
```

### 2.5 Errors

| Observation | Exception | State change | Caller should |
|---|---|---|---|
| network error, timeout, 408, 429, 5xx, non-JSON 2xx | `AirseekersTransportError` | none | back off and retry |
| non-JSON 4xx (not 401) | `AirseekersApiError(code=status)` | none | inspect `code`, `path` |
| auth failure after one renewal | `AirseekersApiError` | the renewed token is kept | retry later; report if persistent |
| refresh token rejected | (internal) | falls back to login | — |
| login rejected | `AirseekersAuthError` | terminal flag set | ask the user for new credentials, then `set_credentials` |
| envelope `code` ≠ 0, not an empty code | `AirseekersApiError` | none | inspect `code` (e.g. 309 offline, -107 not allowed) |
| WHEP offer refused | `AirseekersApiError(code=status)` | none | fetch a fresh URL and retry |
| Foxglove bridge unreachable or not Foxglove | `AirseekersTransportError` | none | retry later |

## 3. Single homes

| Question | The one place that answers it |
|---|---|
| Is this HTTP status transient? | `cloud/transport.py::is_transient_status` |
| Is this response an auth failure? | `cloud/transport.py::CloudTransport._is_auth_failure` (+ `const.AUTH_ERROR_KEYWORDS`) |
| Is this envelope a success? | `const.SUCCESS_CODE`, checked in `CloudTransport.request` |
| Which non-success codes mean "empty"? | the `empty_codes` argument at the one call site, constants in `const.py` |
| Do we have a usable token / who renews it? | `CloudTransport._token` |
| How is a token printed? | `cloud/transport.py::fingerprint` |
| How is a secret kept out of `repr`? | `field(repr=False)` in `models.py`; custom `__repr__` on `CloudTransport`, `AirseekersCloud` |
| Which host do we talk to? | `CloudTransport.base_url` (`const.API_BASE_URL`, then login `host`) |
| `pkg/Type` → `pkg/msg/Type`? | `local/ros1.py::to_type_path` |
| What is the public API? | `pyairseekers/__init__.py::__all__` |

## 4. Extension recipes

**A new cloud endpoint**: path in `const.py`, one method in `cloud/api.py`
(two or three lines: build body, call the requester, shape the result), a row
in `TestEndpointTable` in `tests/unit/cloud/test_api.py`, a row in
`docs/api/cloud.md` with its evidence level. Add a fake-server route only when
the endpoint has behaviour worth testing over the wire.

**A non-success code that means "nothing here"**: name it in `const.py`, pass
it as `empty_codes` from the one method, document it in `docs/api/cloud.md`.
Never compare a raw code at a call site.

**A typed response model**: only once the shape is verified (D4). Add it to
`models.py` with `repr=False` on anything secret; decode in the one API
method; a missing required field raises `AirseekersApiError` naming it.

**A local command**: not without a decision entry (CONSTITUTION §2).

**A new transport (MQTT, BLE)**: promote it out of D9 by giving it a protocol
seam, a fake, tests, and a page under `docs/api/`, documented here first.

## 5. What the library does not do

- It does not send commands to the mower over the local bridge.
- It does not handle WebRTC media; it brokers the SDP exchange only.
- It does not poll, schedule, reconnect or keep tokens warm. Hosts call; the
  library renews when a call needs it.
- It does not know about Home Assistant. Entity mapping, persistence and
  reconnect policy belong to the host.
- It does not interpret mower state beyond naming wire values in `const.py`.
