# Backlog

Open work only; finished items are deleted.

## Library

- `tests/live/` tier: opt-in, read-only smoke test (devices, full-status,
  config, one Foxglove topic) from `AIRSEEKERS_*` env vars.
- Foxglove coverage (66 %): advertise/unadvertise while connected, status
  ops, schema registration failure, malformed frames.
- Typed models for verified shapes (full-status sections, task, task unit,
  map feature) once captures cover them (D4).
- A `start_mowing_advanced`-style task builder in the library (zone names →
  `task_units` with `cut_mode`), moved out of the Home Assistant integration.
- Promote MQTT and BLE out of D9, or delete them, once a mower is on hand.
- Configure PyPI trusted publishing and a `release.yml` before the first
  release; the Home Assistant integration pins `pyairseekers==0.1.0`.

## Documentation

- Page for local topics with message fields observed per topic
  (`docs/api/local.md` lists topics only).
