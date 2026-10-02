# pyairseekers

Async Python client for the Airseekers Tron robotic mower.

| Transport | Module | What for |
|---|---|---|
| Cloud REST | `pyairseekers.AirseekersCloud` | commands, settings, tasks, maps, account data |
| Local Foxglove bridge (`ws://<mower-ip>:8765`) | `pyairseekers.FoxgloveClient`, `pyairseekers.MowerController` | live telemetry; verified `stop` / `pause` |
| Local HTTP API (`http://<mower-ip>:13344`) | `pyairseekers.LocalApi` | maps; task start / pause / resume / stop / dock (unverified, D17) |
| WHEP on the vendor's SRS server | `pyairseekers.whep_play` | live camera video |
| Cloud MQTT / BLE | `pyairseekers.mqtt` / `pyairseekers.ble` | experimental |

There is no published Airseekers API. Every endpoint in
[`docs/api/`](docs/api/README.md) is marked verified, observed or inferred.

```bash
pip install pyairseekers
```

```python
async with aiohttp.ClientSession() as session:
    cloud = AirseekersCloud(email, password, session)
    devices = await cloud.get_devices()
    await cloud.dock(devices[0]["sn"])
```

See [`examples/basic.py`](examples/basic.py). Failed commands raise
`AirseekersApiError` (with `.code`); network trouble raises
`AirseekersTransportError`; rejected credentials raise `AirseekersAuthError`
and stay rejected until `set_credentials()`.

## Development

Read [`CONSTITUTION.md`](CONSTITUTION.md) and [`CONTRIBUTING.md`](CONTRIBUTING.md).

```bash
uv sync
uv run pre-commit run --all-files
```

## Credits

- Cloud endpoint discovery: [AdrianTIonut/airseekers-tron-ha](https://github.com/AdrianTIonut/airseekers-tron-ha)
- Foxglove client and ROS1 deserializer: [Shimmi/airseekers-tron-ha](https://github.com/Shimmi/airseekers-tron-ha)
