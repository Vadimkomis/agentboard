"""Framework-independent security helpers for the local browser UI."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

_SESSION_SIGNATURE_BYTES = 32
_DEFAULT_SESSION_TTL_SECONDS = 8 * 60 * 60


@dataclass(frozen=True, slots=True)
class CsrfSession:
    """Signed state used to bind CSRF tokens to one local browser."""

    csrf_token: str
    issued_at: int
    expires_at: int


def generate_csrf_token() -> str:
    """Generate an unpredictable token suitable for a form field."""

    return secrets.token_urlsafe(32)


def sign_session(
    secret: str,
    *,
    csrf_token: str,
    now: int | None = None,
    ttl_seconds: int = _DEFAULT_SESSION_TTL_SECONDS,
) -> str:
    """Create a signed, expiring browser-session cookie value."""

    secret_bytes = _validated_session_secret(secret)
    if not csrf_token:
        raise ValueError("CSRF token must not be empty")
    if ttl_seconds <= 0:
        raise ValueError("session TTL must be positive")
    issued_at = int(time.time()) if now is None else now
    payload = _session_payload(csrf_token, issued_at, issued_at + ttl_seconds)
    signature = hmac.new(secret_bytes, payload, hashlib.sha256).digest()
    return f"{_encode_base64url(payload)}.{_encode_base64url(signature)}"


def verify_session(
    secret: str,
    cookie_value: str | None,
    *,
    now: int | None = None,
) -> CsrfSession | None:
    """Return signed CSRF state, or ``None`` for an invalid cookie."""

    secret_bytes = _validated_session_secret(secret)
    parts = cookie_value.split(".") if cookie_value else []
    if len(parts) != 2:
        return None
    try:
        payload = _decode_base64url(parts[0])
        supplied_signature = _decode_base64url(parts[1])
    except (ValueError, binascii.Error):
        return None
    expected_signature = hmac.new(secret_bytes, payload, hashlib.sha256).digest()
    if len(supplied_signature) != _SESSION_SIGNATURE_BYTES:
        return None
    if not _constant_time_bytes_equal(supplied_signature, expected_signature):
        return None
    claims = _decode_session_claims(payload)
    current_time = int(time.time()) if now is None else now
    if claims is None or claims.expires_at <= current_time:
        return None
    return claims


def verify_csrf_token(expected: str, submitted: str | None) -> bool:
    """Compare a submitted form token with signed browser-session state."""

    if not expected or not submitted:
        return False
    return _constant_time_text_equal(expected, submitted)


def _validated_session_secret(secret: str) -> bytes:
    secret_bytes = secret.encode("utf-8")
    if len(secret_bytes) < 32:
        raise ValueError("session secret must be at least 32 bytes")
    return secret_bytes


def _session_payload(csrf_token: str, issued_at: int, expires_at: int) -> bytes:
    return json.dumps(
        {"csrf": csrf_token, "exp": expires_at, "iat": issued_at},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _decode_session_claims(payload: bytes) -> CsrfSession | None:
    try:
        value: object = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(value, dict) or set(value) != {"csrf", "exp", "iat"}:
        return None
    csrf_token = value.get("csrf")
    expires_at = value.get("exp")
    issued_at = value.get("iat")
    if not isinstance(csrf_token, str) or not csrf_token:
        return None
    if type(expires_at) is not int or type(issued_at) is not int:
        return None
    if expires_at <= issued_at:
        return None
    return CsrfSession(csrf_token, issued_at, expires_at)


def _encode_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_base64url(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.b64decode(value + padding, altchars=b"-_", validate=True)


def _constant_time_bytes_equal(left: bytes, right: bytes) -> bool:
    return hmac.compare_digest(left, right)


def _constant_time_text_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left, right)
