# Testing

`tests/meta/test_conventions.py` asserts the mechanical parts of this
document; review catches the rest.

## 1. Tiers

| Tier | Directory | Touches | Runs |
|---|---|---|---|
| unit | `tests/unit/` | one module, hand-written fakes, no sockets | every commit, < 2 s |
| integration | `tests/integration/` | the real client against `tests/integration/fakeserver/` over loopback | every commit, < 10 s |
| meta | `tests/meta/` | the source tree itself (layout, layers, conventions) | every commit |
| live | `tests/live/` | the real cloud and mower; marked `live`, skipped unless `AIRSEEKERS_EMAIL`, `AIRSEEKERS_PASSWORD` (and `AIRSEEKERS_MOWER_IP` for local) are set; read-only calls only | on demand |

A unit test that imports `fakeserver` is an integration test in the wrong
directory. A live test never sends a motion command.

## 2. Layout mirrors the package

```
pyairseekers/cloud/api.py     →  tests/unit/cloud/test_api.py
pyairseekers/local/ros1.py    →  tests/unit/local/test_ros1.py
pyairseekers/local/foxglove.py → tests/integration/test_foxglove.py
pyairseekers/live.py          →  tests/integration/test_live.py
```

A module is mirrored by `tests/unit/<path>/test_<module>.py` or, when it is
I/O-only, `tests/integration/test_<module>.py`. Exemptions live in
`EXEMPT_FROM_MIRRORING` with a reason. Tests are grouped in classes named for
the behaviour (`class TestRenewal:`) with names that read as sentences.

Shared code lives in one place:

- `tests/_helpers.py`: fixture identities, `SECRET_VALUES`, `envelope()`,
  SDP samples.
- `tests/unit/_fakes.py`: `FakeRequester` and any future fake.
- `tests/integration/fakeserver/`: `FakeCloud` (cloud + SRS WHEP, with
  `CloudState` fault knobs) and `FakeBridge` (Foxglove).
- `tests/conftest.py`: global safety nets only. The autouse
  `no_secrets_in_logs` fixture fails any test whose `pyairseekers` logs carry
  a fixture secret.

## 3. Doubles

Real object → hand-written fake. `unittest.mock` is not imported under
`tests/`: a `MagicMock` answers every attribute forever, so a renamed method
keeps passing. Assert on outcomes (the returned data, the raised exception,
the recorded request) rather than on call plumbing, unless the call is the
contract ("one login for a burst of 401s").

## 4. Time and concurrency

- `await asyncio.sleep(x)` with `x > 0` is not synchronisation. Wait on an
  `asyncio.Event` or a queue; `asyncio.sleep(0)` yields one loop turn.
- Bound every wait with `asyncio.wait_for`.
- `asyncio_mode = "auto"`; no `@pytest.mark.asyncio`.
- Concurrency tests gate the fake on an `asyncio.Event`
  (`CloudState.login_gate`) so the interleaving is deterministic.

## 5. Secrets in tests

Fixture credentials are obviously fake (`not-a-real-password`,
`.invalid` hosts). Tests assert that `repr()` and `str(exc)` do not contain
them. Live tests read credentials from the environment and never print them.

## 6. Regression contract

A regression test was written against the broken code and seen red, is marked
`@pytest.mark.regression`, is named for the behaviour, has a docstring saying
what the code did wrong, and lives beside the module it pins.

## 7. Gates

- `pytest --cov` must not drop below `fail_under` in `pyproject.toml`. It is a
  floor, not a target.
- `filterwarnings = error`: a warning is a failure.
- Pre-commit runs ruff, ruff-format, ty and the unit + meta tiers; CI runs
  everything except `live`.
