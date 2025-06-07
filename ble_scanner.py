"""
Bluetooth Low Energy device scanner for Airseekers devices.
"""

import logging
from typing import Optional

from models import BLEDevice

_LOGGER = logging.getLogger(__name__)

class BLEDeviceScanner:
    def __init__(self, service_uuids: list[str]):
        self.service_uuids = service_uuids
        self.discovered_devices: dict[str, BLEDevice] = {}
        
    async def scan_for_devices(self, scan_duration: int = 10) -> list[BLEDevice]:
        try:
            import bleak
            
            _LOGGER.info(f"Scanning for BLE devices for {scan_duration} seconds...")
            
            discovered = await bleak.BleakScanner.discover(timeout=scan_duration, return_adv=True)
            
            airseekers_devices = []
            
            for device, adv_data in discovered.values():
                if any(uuid in str(adv_data.service_uuids) for uuid in self.service_uuids):
                    ble_device = BLEDevice(
                        address=device.address,
                        name=device.name,
                        rssi=adv_data.rssi
                    )
                    airseekers_devices.append(ble_device)
                    self.discovered_devices[device.address] = ble_device
                    
            _LOGGER.info(f"Found {len(airseekers_devices)} Airseekers devices")
            return airseekers_devices
            
        except ImportError:
            _LOGGER.error("bleak library not installed. BLE scanning unavailable.")
            return []
        except Exception as e:
            _LOGGER.error(f"Error during BLE scan: {e}")
            return []

    def get_device_by_address(self, address: str) -> Optional[BLEDevice]:
        return self.discovered_devices.get(address)