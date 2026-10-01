"""Value objects returned by pyairseekers.

Cloud responses stay raw mappings until a shape is verified on hardware (D4);
only shapes the library itself builds or consumes are modelled here.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class IoTCert:
    """MQTT credentials returned by ``/api/web/device/iot-cert``."""

    ca: str
    cert_key: str = field(repr=False)
    mqtt_broker: str
    mqtt_client_id: str
    private_key: str = field(repr=False)


@dataclass(frozen=True)
class BLEDevice:
    """An Airseekers device found by a BLE scan."""

    address: str
    name: str | None = None
    rssi: int | None = None
    is_connected: bool = False


@dataclass(frozen=True)
class LiveStream:
    """A playing WHEP session on the vendor's SRS media server."""

    answer_sdp: str = field(repr=False)
    # WHEP session resource; DELETE it to stop playback
    resource_url: str | None = field(repr=False)
