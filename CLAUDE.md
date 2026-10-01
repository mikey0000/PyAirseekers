# CLAUDE.md

Guidance for agents working in this repository. Read `CONSTITUTION.md`
first; it is short and it is binding.

## What this is

`pyairseekers`: an async Python client for the Airseekers Tron robotic mower.
Three independent transports: the cloud REST API (commands, settings, account
data), the mower's local Foxglove bridge (read-only telemetry), and WHEP live
video on the vendor's SRS server. MQTT and BLE are experimental (D9). There is
no published API; everything is evidence-graded in `docs/api/`.

## Commands

```bash
uv sync
uv run ruff check --fix . && uv run ruff format .
uv run ty check
uv run pytest                      # unit + integration + meta
uv run pytest tests/unit           # fast tier
uv run pytest -m live              # needs AIRSEEKERS_EMAIL / _PASSWORD / _MOWER_IP
uv run pre-commit run --all-files
```

## Where things are

| Need | Read |
|---|---|
| the rules | `CONSTITUTION.md` |
| the map (layers, flows, single homes, recipes) | `docs/architecture.md` |
| how to write code | `docs/code_style.md` |
| how to write tests | `docs/testing.md` |
| why something is the way it is | `docs/decisions.md` (numbered; cite as D5) |
| what the API is, and how sure we are | `docs/api/*.md` |
| what we do not know | `docs/open_questions.md` (cite as Q3) |
| what is left to do | `docs/backlog.md` |
| reverse-engineering notes | `docs/protocol_analysis.md`, `docs/extracted_protobuf_definitions.proto` |

## Rules of work

- **Safety first.** No local command path (CONSTITUTION §2). Cloud commands
  move a real mower: never call one from a test outside the `live` tier.
- **Audit before adding.** Every concern has a single home
  (`architecture.md` §3). If you are writing a check that exists elsewhere,
  stop and extend the existing site.
- **Endpoint recipe.** An endpoint is added in four places: the path in
  `const.py`, one method in `cloud/api.py`, a row in the endpoint table test
  (`tests/unit/cloud/test_api.py`), and a row in `docs/api/cloud.md` with its
  evidence level. Fake-server route only if it has behaviour worth testing.
- **Tests before merge, in the right tier.** Regression tests are seen red
  first and marked `regression`. Launch the `test-reviewer` agent over any
  test file you touched and fix its blocking findings before reporting done.
- **Reviews.** Non-trivial changes get the `code-reviewer` agent
  (`.claude/agents/`) before they are reported complete.
- **Decisions are written down.** A new non-obvious choice is a new `Dn`; a
  new unknown is a `Qn`. Promoting an endpoint to verified needs a capture.
- **No secrets anywhere** in logs, reprs, exceptions, tests or commit messages
  (the live-stream URL is a secret: it carries a signed token).
- **Comments say why, in one or two lines, or do not exist.**
- **Commits**: imperative subject, one change per commit, no attribution
  trailers of any kind.

## Layout

```
pyairseekers/
  __init__.py  const.py  exceptions.py  models.py  live.py
  cloud/       transport.py (CloudTransport, Requester)  api.py (AirseekersCloud)
  local/       foxglove.py (FoxgloveClient)  ros1.py (runtime ROS1 decoder)
  mqtt.py  ble.py              experimental (D9)
tests/
  conftest.py  _helpers.py      secret-leak guard, shared builders
  unit/        _fakes.py  cloud/ local/ test_models.py
  integration/ fakeserver/ (cloud + SRS, Foxglove bridge)  test_transport.py test_live.py test_foxglove.py
  meta/        test_conventions.py
docs/          architecture.md code_style.md testing.md decisions.md backlog.md open_questions.md api/
examples/      basic.py
```
