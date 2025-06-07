"""
MQTT client for real-time Airseekers device communication using async paho-mqtt.
"""

import asyncio
import json
import logging
import ssl
import tempfile
import os
from typing import Callable, Optional, Union

from paho.mqtt.client import Client, MQTTMessage, MQTTv311, MQTT_ERR_SUCCESS
from paho.mqtt.enums import CallbackAPIVersion

from models import IoTCertResponse

_LOGGER = logging.getLogger(__name__)

class MQTTClient:
    def __init__(self, iot_cert: IoTCertResponse, message_callback: Optional[Callable] = None):
        self.iot_cert = iot_cert
        self.message_callback = message_callback
        self.client: Optional[Client] = None
        self.is_connected = False
        self._temp_dir = None
        self._connection_event = asyncio.Event()
        self._disconnect_event = asyncio.Event()
        self._subscribe_events: dict[str, asyncio.Event] = {}
        self._publish_events: dict[int, asyncio.Event] = {}
        self._publish_results: dict[int, bool] = {}
        
    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            self.is_connected = True
            self._connection_event.set()
            _LOGGER.info("Successfully connected to MQTT broker")
        else:
            _LOGGER.error(f"Failed to connect to MQTT broker: {reason_code}")
            
    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        self.is_connected = False
        self._connection_event.clear()
        self._disconnect_event.set()
        _LOGGER.info("Disconnected from MQTT broker")
        
    def _on_message(self, client, userdata, msg: MQTTMessage):
        if self.message_callback:
            try:
                payload = json.loads(msg.payload.decode())
            except json.JSONDecodeError:
                payload = msg.payload.decode()
                
            # Schedule the callback to run in the event loop
            asyncio.create_task(self.message_callback(msg.topic, payload))

    def _on_subscribe(self, client, userdata, mid, reason_codes, properties=None):
        topic = userdata.get('subscribe_topic') if userdata else None
        if topic and topic in self._subscribe_events:
            self._subscribe_events[topic].set()
            _LOGGER.info(f"Successfully subscribed to topic: {topic}")
    
    def _on_publish(self, client, userdata, mid, reason_code=None, properties=None):
        if mid in self._publish_events:
            self._publish_results[mid] = reason_code == MQTT_ERR_SUCCESS
            self._publish_events[mid].set()

    async def connect(self) -> bool:
        try:
            self._temp_dir = tempfile.mkdtemp()
            ca_file = os.path.join(self._temp_dir, "ca.crt")
            cert_file = os.path.join(self._temp_dir, "cert.pem")
            key_file = os.path.join(self._temp_dir, "private.key")
            
            with open(ca_file, "w") as f:
                f.write(self.iot_cert.ca)
            with open(cert_file, "w") as f:
                f.write(self.iot_cert.cert_key)
            with open(key_file, "w") as f:
                f.write(self.iot_cert.private_key)
            
            broker_host, broker_port = self.iot_cert.mqtt_broker.split(":")
            
            self.client = Client(
                callback_api_version=CallbackAPIVersion.VERSION2,
                client_id=self.iot_cert.mqtt_client_id,
                protocol=MQTTv311
            )
            
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message
            self.client.on_subscribe = self._on_subscribe
            self.client.on_publish = self._on_publish
            
            self.client.tls_set(
                ca_certs=ca_file,
                certfile=cert_file,
                keyfile=key_file,
                cert_reqs=ssl.CERT_REQUIRED,
                tls_version=ssl.PROTOCOL_TLS,
                ciphers=None
            )
            
            # Start the network loop in a separate thread
            self.client.loop_start()
            
            # Connect asynchronously
            result = self.client.connect(broker_host, int(broker_port), 60)
            if result != MQTT_ERR_SUCCESS:
                raise Exception(f"Failed to initiate connection: {result}")
            
            # Wait for connection
            await asyncio.wait_for(self._connection_event.wait(), timeout=10.0)
            return True
            
        except Exception as e:
            _LOGGER.error(f"Failed to connect to MQTT broker: {e}")
            return False
    
    async def disconnect(self):
        if self.client and self.is_connected:
            try:
                self._disconnect_event.clear()
                self.client.disconnect()
                
                # Wait for disconnect confirmation
                await asyncio.wait_for(self._disconnect_event.wait(), timeout=5.0)
                self.client.loop_stop()
                self.is_connected = False
                _LOGGER.info("Disconnected from MQTT broker")
            except asyncio.TimeoutError:
                _LOGGER.warning("Disconnect timeout, forcing stop")
                self.client.loop_stop()
                self.is_connected = False
            except Exception as e:
                _LOGGER.error(f"Error disconnecting from MQTT: {e}")
        
        if self._temp_dir:
            try:
                import shutil
                shutil.rmtree(self._temp_dir)
            except Exception as e:
                _LOGGER.error(f"Error cleaning up temp files: {e}")
    
    async def subscribe(self, topic: str) -> bool:
        if not self.is_connected or not self.client:
            raise RuntimeError("MQTT client not connected")
        
        # Create an event for this subscription
        self._subscribe_events[topic] = asyncio.Event()
        
        # Set userdata to track which topic we're subscribing to
        self.client.user_data_set({'subscribe_topic': topic})
        
        result, mid = self.client.subscribe(topic)
        if result != MQTT_ERR_SUCCESS:
            del self._subscribe_events[topic]
            _LOGGER.error(f"Failed to subscribe to {topic}: {result}")
            return False
        
        try:
            # Wait for subscription confirmation
            await asyncio.wait_for(self._subscribe_events[topic].wait(), timeout=5.0)
            del self._subscribe_events[topic]
            _LOGGER.info(f"Subscribed to MQTT topic: {topic}")
            return True
        except asyncio.TimeoutError:
            del self._subscribe_events[topic]
            _LOGGER.error(f"Subscription timeout for topic: {topic}")
            return False
    
    async def publish(self, topic: str, payload: Union[str, dict]) -> bool:
        if not self.is_connected or not self.client:
            raise RuntimeError("MQTT client not connected")
            
        if isinstance(payload, dict):
            payload = json.dumps(payload)
        
        # Create an event for this publish
        msg_info = self.client.publish(topic, payload)
        mid = msg_info.mid
        
        if not msg_info.is_published():
            self._publish_events[mid] = asyncio.Event()
            
            try:
                # Wait for publish confirmation
                await asyncio.wait_for(self._publish_events[mid].wait(), timeout=5.0)
                success = self._publish_results.get(mid, False)
                
                # Clean up
                del self._publish_events[mid]
                if mid in self._publish_results:
                    del self._publish_results[mid]
                
                if success:
                    _LOGGER.debug(f"Published to MQTT topic {topic}: {payload}")
                else:
                    _LOGGER.error(f"Failed to publish to MQTT topic {topic}")
                
                return success
                
            except asyncio.TimeoutError:
                # Clean up on timeout
                if mid in self._publish_events:
                    del self._publish_events[mid]
                if mid in self._publish_results:
                    del self._publish_results[mid]
                _LOGGER.error(f"Publish timeout for topic: {topic}")
                return False
        else:
            _LOGGER.debug(f"Published to MQTT topic {topic}: {payload}")
            return True
    
    def is_connection_alive(self) -> bool:
        return self.is_connected and self.client is not None