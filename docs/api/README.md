# API reference

What the package talks to, in the package's terms, with an evidence level for
every entry (D1):

- **verified**: exercised against a real Tron, response seen.
- **observed**: seen in app traffic or app analysis; not exercised here.
- **inferred**: guessed from naming or neighbours.

| Page | Transport | Module |
|---|---|---|
| [cloud](cloud.md) | REST, `https://cloud-eu.airseekers-robotics.com` | `pyairseekers/cloud/` |
| [live](live.md) | WHEP on SRS 6, `http://living-eu.airseekers-robotics.com` | `pyairseekers/live.py` |
| [local](local.md) | Foxglove WebSocket, `ws://<mower-ip>:8765` | `pyairseekers/local/` |
| [mqtt](mqtt.md) | MQTT v5 over mutual TLS (broker from `iot-cert`) | `pyairseekers/mqtt.py` (experimental, D9) |

Older reverse-engineering notes: `../protocol_analysis.md`,
`../extracted_protobuf_definitions.proto`.
