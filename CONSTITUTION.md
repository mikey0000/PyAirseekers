# Constitution

These are the rules that do not bend. Everything else in `docs/` explains how
to apply them; this file says what they are. A change that breaks one of these
needs a new numbered entry in `docs/decisions.md` that supersedes the rule, not
a quiet exception.

## 1. Evidence, not guesswork

There is no published Airseekers API. Every endpoint, field and code in this
package comes from observed traffic or a real mower, and `docs/api/` records
how sure we are: **verified** (exercised against a real Tron), **observed**
(seen in app traffic or app analysis, not exercised) or **inferred**. Nothing
is promoted to verified without a capture. Where the evidence is silent, the
gap is a `Qn` in `docs/open_questions.md` and the code takes the conservative
reading, stated in a docstring.

## 2. Local commands only once verified

The mower has blades and drives itself. `pyairseekers.local` subscribes and
decodes freely. The library's own commands go only through
`local/control.py`, only once a decision entry cites on-device verification
of that command and of safe-stop, and every call checks the advertised schema
still matches and confirms the service response. Today that is
`/controller/ctrl` with `stop` and `pause` (D15). `FoxgloveClient.call_service`
is a raw primitive for verification tooling; a host that calls it directly
owns what it sends. Publishing topics (`/cmd_vel`), blade, dock and power
services stay closed until a decision opens them; everything else goes
through the cloud.

## 3. Transports are independent; layers point one way

```
const, exceptions, models  ←  cloud.transport  ←  cloud.api
const, exceptions, models  ←  live
exceptions                 ←  local.ros1  ←  local.foxglove
```

`cloud`, `local` and `live` never import each other. `cloud.api` depends on
the `Requester` protocol, not on `CloudTransport`. Nothing in the package
knows that Home Assistant, or any other host, exists. Hosts compose the
transports (D2).

## 4. All I/O is asynchronous

Every network call is `async`. There is no blocking I/O, no thread pool, and no
global event loop reference. A host may supply its own `aiohttp` session; the
library must work with it and must not close it.

## 5. Errors are typed, scoped and honest

- A non-success response is an exception, never a return value. A command
  that the cloud rejects raises `AirseekersApiError` with the code; it does not
  return `False`. The only exceptions are per-endpoint "nothing here" codes
  listed in `docs/api/cloud.md` (D6).
- Transient failures (network, timeout, 408, 429, 5xx, non-JSON 2xx) are
  `AirseekersTransportError`. They never change credential state.
- A rejected login is terminal: `AirseekersAuthError` is raised, every later
  call fails without touching the network, and only `set_credentials()` clears
  it. No retry timers; a wrong password does not become right by waiting.
- Exactly one renewal per stale token. Concurrent callers that hit the same
  dead token share one renewal.

## 6. Secrets stay secret

The password, access and refresh tokens, IoT private keys, and the signed
`secret` in a live-stream URL never appear in log lines, `repr`, exception
messages or test output. Models holding them redact in `__repr__`. Logs may
carry a token fingerprint and nothing more.

## 7. Wire data is tolerant

The library never crashes on a new field, a missing optional field or an
unexpected type. Cloud responses are returned as mappings until their shape is
verified (D4); a required field that is missing from a modelled response
raises `AirseekersApiError` naming the field.

## 8. Tests are part of the deliverable

Nothing merges without tests in the right tier (`docs/testing.md`). A
regression test has been watched failing against the bug before the fix.
Doubles are real objects or hand-written fakes with the same interface;
`unittest.mock` is not a test double.

## 9. Documentation lives outside the code

Design lives in `docs/`, not in comments. A comment states a constraint the
code cannot express; it is one or two lines and never a paragraph. Every
non-obvious design choice is a numbered entry in `docs/decisions.md`. Open
debt is in `docs/backlog.md`; unknowns are in `docs/open_questions.md`.

## 10. The public surface is deliberate

`pyairseekers.__all__` lists the supported API. Anything not in it may change
without notice. Versioning follows semver; a breaking change to a listed name
bumps the major version (minor while below 1.0).
