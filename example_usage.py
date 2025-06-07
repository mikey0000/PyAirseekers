"""
Example usage of the Airseekers API for Home Assistant integration.
"""

import asyncio
import logging
from main import AirseekersHomeAssistantAPI

logging.basicConfig(level=logging.INFO)

async def message_callback(topic: str, payload):
    print(f"Received MQTT message on {topic}: {payload}")

async def main():
    # Initialize the API with your credentials
    api = AirseekersHomeAssistantAPI(
        email="your-email@example.com",
        password="your-password",
        message_callback=message_callback
    )
    
    # Initialize connection
    if not await api.initialize():
        print("Failed to initialize API")
        return
    
    print("API initialized successfully")
    
    # Discover devices
    devices = await api.discover_devices(scan_ble=True)
    print(f"Found {len(devices['cloud_devices'])} cloud devices")
    print(f"Found {len(devices['ble_devices'])} BLE devices")
    
    # If you have devices, you can control them
    if devices['cloud_devices']:
        device_id = devices['cloud_devices'][0].get('id')
        if device_id:
            # Get device status
            status = await api.get_device_status(device_id)
            print(f"Device status: {status}")
            
            # Control device (lock/unlock)
            success = await api.control_device(device_id, "lock")
            print(f"Lock device: {'Success' if success else 'Failed'}")
            
            # Setup MQTT for real-time updates
            try:
                await api.setup_mqtt()
                subscribe_success = await api.subscribe_to_device_updates(device_id)
                print(f"Subscribe to updates: {'Success' if subscribe_success else 'Failed'}")
                
                # Send a command via MQTT
                publish_success = await api.send_device_command(device_id, {
                    "action": "start_mowing",
                    "cutting_height": 30
                })
                print(f"Send command: {'Success' if publish_success else 'Failed'}")
                
                # Keep connection alive for 10 seconds to receive messages
                print("Listening for MQTT messages for 10 seconds...")
                await asyncio.sleep(10)
                
            except Exception as e:
                print(f"MQTT error: {e}")
            finally:
                await api.disconnect_mqtt()
    
    # BLE device example
    if devices['ble_devices']:
        ble_device = devices['ble_devices'][0]
        print(f"Found BLE device: {ble_device['name']} at {ble_device['address']}")

if __name__ == "__main__":
    asyncio.run(main())