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
  `mqtt.py` predates `docs/api/mqtt.md` and does not follow it (MQTT 3.1.1,
  guessed `device/{id}/...` topics, JSON payloads); rebuild it from the doc
  (MQTT v5, `common/app/{cid}/{sn}/be/up|down`, protobuf `Msg`) rather than
  trusting the current module.
- Configure PyPI trusted publishing and a `release.yml` before the first
  release; the Home Assistant integration pins `pyairseekers==0.1.0`.

- Local commands beyond D15, each needing its own on-device verification:
  `/controller/dock/ctrl` arguments, `/cutter_control`, and `publish` for
  `/cmd_vel` once its watchdog is measured.

- Verify the HTTP task commands on a Tron (Q17) and grade them verified, or
  withdraw them; wrap `/robot/task/info` (WebSocket) as a push source.

## Documentation

- Page for local topics with message fields observed per topic
  (`docs/api/local.md` lists topics only).
