"""Builders and constants shared by more than one test tier."""

from __future__ import annotations

SN = "SN-TEST-0001"
EMAIL = "user@example.invalid"
PASSWORD = "not-a-real-password"
ACCESS_TOKEN = "access-token-test-1"
REFRESH_TOKEN = "refresh-token-test-1"
LIVE_SECRET = "jwt-secret-test"

# Values that must never appear in a log line (constitution §6)
SECRET_VALUES = (PASSWORD, ACCESS_TOKEN, REFRESH_TOKEN, LIVE_SECRET)

OFFER_SDP = "v=0\r\no=- 1 2 IN IP4 127.0.0.1\r\na=recvonly\r\n"
ANSWER_SDP = "v=0\r\no=SRS/6 1 2 IN IP4 0.0.0.0\r\na=ice-lite\r\n"


def envelope(data: object = None, *, code: int = 0, msg: str = "success") -> dict[str, object]:
    """Build a cloud response envelope."""
    return {"code": code, "data": data, "errorCode": 0, "msg": msg}


def leaked_secrets(text: str) -> list[str]:
    """Return every fixture secret that appears in ``text``."""
    return [secret for secret in SECRET_VALUES if secret in text]
