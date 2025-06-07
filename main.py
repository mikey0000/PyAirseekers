"""
Main Home Assistant API wrapper for Airseekers devices.
"""

import logging
from typing import Callable, Optional

from api_client import AirseekersAPI
from ble_scanner import BLEDeviceScanner
from mqtt_client import MQTTClient

_LOGGER = logging.getLogger(__name__)

class AirseekersHomeAssistantAPI:
    def __init__(self, email: str, password: str, message_callback: Optional[Callable] = None):
        self.api = AirseekersAPI(email, password)
        self.ble_scanner = BLEDeviceScanner(self.api.ble_service_uuids)
        self.mqtt_client: Optional[MQTTClient] = None
        self.message_callback = message_callback
        
    async def initialize(self) -> bool:
        try:
            async with self.api:
                await self.api.get_server_host()
                await self.api.login()
                return True
        except Exception as e:
            _LOGGER.error(f"Failed to initialize API: {e}")
            return False

    async def discover_devices(self, scan_ble: bool = True) -> dict[str, list]:
        result = {
            "cloud_devices": [],
            "ble_devices": []
        }
        
        try:
            async with self.api:
                cloud_devices = await self.api.get_devices()
                result["cloud_devices"] = cloud_devices.list
                
                if scan_ble:
                    ble_devices = await self.ble_scanner.scan_for_devices()
                    result["ble_devices"] = [device.dict() for device in ble_devices]
                    
        except Exception as e:
            _LOGGER.error(f"Error discovering devices: {e}")
            
        return result

    async def get_device_status(self, device_id: str) -> dict:
        try:
            async with self.api:
                devices = await self.api.get_devices()
                for device in devices.list:
                    if device.get("id") == device_id:
                        return device
                        
                return {}
        except Exception as e:
            _LOGGER.error(f"Error getting device status: {e}")
            return {}

    async def control_device(self, device_id: str, action: str) -> bool:
        try:
            async with self.api:
                if action == "lock":
                    return await self.api.lock_device(device_id)
                elif action == "unlock":
                    return await self.api.unlock_device(device_id)
                elif action == "bind":
                    return await self.api.bind_device(device_id)
                elif action == "unbind":
                    return await self.api.unbind_device(device_id)
                else:
                    _LOGGER.error(f"Unknown action: {action}")
                    return False
        except Exception as e:
            _LOGGER.error(f"Error controlling device: {e}")
            return False

    async def setup_mqtt(self) -> bool:
        try:
            async with self.api:
                iot_cert = await self.api.get_iot_certificates()
                self.mqtt_client = MQTTClient(iot_cert, self.message_callback)
                return await self.mqtt_client.connect()
        except Exception as e:
            _LOGGER.error(f"Error setting up MQTT: {e}")
            return False

    async def subscribe_to_device_updates(self, device_id: str) -> bool:
        if not self.mqtt_client or not self.mqtt_client.is_connected:
            raise RuntimeError("MQTT client not connected. Call setup_mqtt() first.")
        
        topic = f"device/{device_id}/status"
        return await self.mqtt_client.subscribe(topic)

    async def send_device_command(self, device_id: str, command: dict) -> bool:
        if not self.mqtt_client or not self.mqtt_client.is_connected:
            raise RuntimeError("MQTT client not connected. Call setup_mqtt() first.")
        
        topic = f"device/{device_id}/command"
        return await self.mqtt_client.publish(topic, command)

    async def disconnect_mqtt(self):
        if self.mqtt_client:
            await self.mqtt_client.disconnect()

    def is_mqtt_connected(self) -> bool:
        return self.mqtt_client is not None and self.mqtt_client.is_connection_alive()