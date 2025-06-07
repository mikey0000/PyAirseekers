"""
Core API client for Airseekers cloud services.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urljoin

import aiohttp

from models import (
    ApiResponse, LoginResponse, ServerHostResponse, 
    IoTCertResponse, DeviceListResponse
)

_LOGGER = logging.getLogger(__name__)

class AirseekersAPI:
    def __init__(self, email: str, password: str, session: Optional[aiohttp.ClientSession] = None):
        self.email = email
        self.password = password
        self.session = session
        self._should_close_session = session is None
        
        self.base_url = "https://cloud-eu.airseekers-robotics.com"
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.token_expires_at: Optional[datetime] = None
        
        self.app_version = "1.0.7(2025052706)"
        
        self.ble_service_uuids = [
            "b725d2d0-353a-11f0-8d6e-09546e761b8b",
            "88992250-360c-11f0-90a3-792c334dd14f", 
            "3f1dbe80-3538-11f0-8d6e-09546e761b8b"
        ]

    async def __aenter__(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._should_close_session and self.session:
            await self.session.close()

    def _get_headers(self, include_auth: bool = True) -> dict[str, str]:
        headers = {
            "accept": "application/json,*/*",
            "accept-encoding": "gzip",
            "accept-language": "en-US",
            "app-version": self.app_version,
            "content-type": "application/json"
        }
        
        if include_auth and self.access_token:
            headers["authorization"] = f"Bearer {self.access_token}"
        elif include_auth:
            headers["authorization"] = "Bearer"
            
        return headers

    async def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        data: Optional[dict] = None,
        include_auth: bool = True
    ) -> ApiResponse:
        if not self.session:
            raise RuntimeError("Session not initialized")
            
        url = urljoin(self.base_url, endpoint)
        headers = self._get_headers(include_auth)
        
        _LOGGER.debug(f"Making {method} request to {url}")
        
        kwargs = {"headers": headers}
        if data:
            kwargs["json"] = data
            
        async with self.session.request(method, url, **kwargs) as response:
            response_data = await response.json()
            return ApiResponse(**response_data)

    async def get_server_host(self) -> str:
        response = await self._make_request("GET", "/api/web/server-host", include_auth=False)
        if response.code == 0 and response.data:
            host_response = ServerHostResponse(**response.data)
            self.base_url = host_response.host
            return host_response.host
        raise Exception(f"Failed to get server host: {response.msg}")

    async def login(self) -> LoginResponse:
        login_data = {
            "email": self.email,
            "password": self.password
        }
        
        response = await self._make_request("POST", "/user/login", login_data, include_auth=False)
        
        if response.code == 0 and response.data:
            login_response = LoginResponse(**response.data)
            self.access_token = login_response.access_token
            self.refresh_token = login_response.refresh_token
            self.base_url = login_response.host
            
            self.token_expires_at = datetime.now() + timedelta(hours=23)
            
            _LOGGER.info("Successfully logged in to Airseekers API")
            return login_response
        
        raise Exception(f"Login failed: {response.msg}")

    async def refresh_access_token(self) -> bool:
        if not self.refresh_token:
            return False
            
        try:
            response = await self._make_request("POST", "/api/web/user/refresh-token", {
                "refresh_token": self.refresh_token
            })
            
            if response.code == 0 and response.data:
                self.access_token = response.data.get("access_token")
                self.token_expires_at = datetime.now() + timedelta(hours=23)
                _LOGGER.info("Successfully refreshed access token")
                return True
        except Exception as e:
            _LOGGER.error(f"Failed to refresh token: {e}")
            
        return False

    async def ensure_authenticated(self) -> bool:
        if not self.access_token:
            await self.login()
            return True
            
        if self.token_expires_at and datetime.now() >= self.token_expires_at:
            if not await self.refresh_access_token():
                await self.login()
            return True
            
        return True

    async def get_iot_certificates(self) -> IoTCertResponse:
        await self.ensure_authenticated()
        response = await self._make_request("POST", "/api/web/device/iot-cert", {})
        
        if response.code == 0 and response.data:
            return IoTCertResponse(**response.data)
        
        raise Exception(f"Failed to get IoT certificates: {response.msg}")

    async def get_devices(self) -> DeviceListResponse:
        await self.ensure_authenticated()
        response = await self._make_request("GET", "/api/web/device")
        
        if response.code == 0 and response.data:
            return DeviceListResponse(**response.data)
        
        raise Exception(f"Failed to get devices: {response.msg}")

    async def is_user_authorized(self) -> bool:
        await self.ensure_authenticated()
        response = await self._make_request("GET", "/api/web/user/is-authorized?123=1")
        return response.code == 0

    async def bind_device(self, device_id: str) -> bool:
        await self.ensure_authenticated()
        response = await self._make_request("POST", "/api/web/device/bind", {"device_id": device_id})
        return response.code == 0

    async def unbind_device(self, device_id: str) -> bool:
        await self.ensure_authenticated()
        response = await self._make_request("POST", "/api/web/device/unbind", {"device_id": device_id})
        return response.code == 0

    async def lock_device(self, device_id: str) -> bool:
        await self.ensure_authenticated()
        response = await self._make_request("POST", "/api/web/device/lock", {"device_id": device_id})
        return response.code == 0

    async def unlock_device(self, device_id: str) -> bool:
        await self.ensure_authenticated()
        response = await self._make_request("POST", "/api/web/device/unlock", {"device_id": device_id})
        return response.code == 0

    async def get_device_map(self, device_id: str) -> dict:
        await self.ensure_authenticated()
        response = await self._make_request("GET", f"/api/web/device/map?device_id={device_id}")
        
        if response.code == 0:
            return response.data or {}
        
        raise Exception(f"Failed to get device map: {response.msg}")

    async def get_latest_firmware(self, device_id: str) -> dict:
        await self.ensure_authenticated()
        response = await self._make_request("GET", f"/api/web/firmware/latest?device_id={device_id}")
        
        if response.code == 0:
            return response.data or {}
        
        raise Exception(f"Failed to get latest firmware: {response.msg}")

    async def upgrade_firmware(self, device_id: str) -> bool:
        await self.ensure_authenticated()
        response = await self._make_request("POST", "/api/web/firmware/upgrade", {"device_id": device_id})
        return response.code == 0