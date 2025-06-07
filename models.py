"""
Pydantic models for Airseekers API responses.
"""

from typing import Optional, Union
from pydantic import BaseModel

class ApiResponse(BaseModel):
    code: int
    data: Optional[Union[dict, list]] = None
    errorCode: int
    msg: str

class LoginResponse(BaseModel):
    access_token: str
    host: str
    language: str = ""
    refresh_token: str

class ServerHostResponse(BaseModel):
    host: str

class IoTCertResponse(BaseModel):
    ca: str
    cert_key: str
    mqtt_broker: str
    mqtt_client_id: str
    private_key: str

class DeviceListResponse(BaseModel):
    list: list[dict]
    total: int

class BLEDevice(BaseModel):
    address: str
    name: Optional[str] = None
    rssi: Optional[int] = None
    is_connected: bool = False