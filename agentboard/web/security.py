"""Framework-independent security helpers for the owner-only browser UI."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import secrets
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl, unquote, urlsplit, urlunsplit

_HASH_SCHEME = "pbkdf2_sha256"
_DEFAULT_PASSWORD_ITERATIONS = 310_000
_MIN_PASSWORD_ITERATIONS = 100_000
_MAX_PASSWORD_ITERATIONS = 1_000_000
_PASSWORD_SALT_BYTES = 16
_PASSWORD_DIGEST_BYTES = 32
_SESSION_SIGNATURE_BYTES = 32
_DEFAULT_SESSION_TTL_SECONDS = 8 * 60 * 60
_INVALID_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")


class FormDecodeError(ValueError):
    """Raised when an URL-encoded form is unsafe or malformed."""


@dataclass(frozen=True, slots=True)
class SessionClaims:
    """Authenticated owner-session claims."""

    csrf_token: str
    issued_at: int
    expires_at: int


def hash_owner_password(
    password: str,
    *,
    salt: bytes | None = None,
    iterations: int = _DEFAULT_PASSWORD_ITERATIONS,
) -> str:
    """Return a versioned PBKDF2-SHA256 owner-password hash."""

    _validate_password_parameters(salt, iterations)
    resolved_salt = secrets.token_bytes(_PASSWORD_SALT_BYTES) if salt is None else salt
    digest = _derive_password(password, resolved_salt, iterations)
    return "$".join(
        (
            _HASH_SCHEME,
            str(iterations),
            _encode_base64url(resolved_salt),
            _encode_base64url(digest),
        )
    )


def verify_owner_password(password: str, encoded: str) -> bool:
    """Verify an owner password without leaking digest mismatch timing."""

    components = _parse_password_hash(encoded)
    if components is None:
        return False
    iterations, salt, expected_digest = components
    actual_digest = _derive_password(password, salt, iterations)
    return _constant_time_bytes_equal(actual_digest, expected_digest)


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
    """Create a signed, expiring owner-session cookie value."""

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
) -> SessionClaims | None:
    """Return authenticated session claims, or ``None`` for an invalid cookie."""

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
    """Compare a submitted form token with authenticated session state."""

    if not expected or not submitted:
        return False
    return _constant_time_text_equal(expected, submitted)


def normalize_local_redirect(
    value: str | None,
    *,
    default: str = "/projects",
) -> str:
    """Normalize a post-login redirect and reject external or ambiguous URLs."""

    if not _is_safe_local_redirect(default):
        raise ValueError("redirect default must be a safe local path")
    target = value if value and _is_safe_local_redirect(value) else default
    parts = urlsplit(target)
    return urlunsplit(("", "", parts.path, parts.query, ""))


def parse_urlencoded_form(
    body: bytes,
    *,
    max_bytes: int = 16_384,
    max_fields: int = 32,
) -> dict[str, str]:
    """Decode a small, unambiguous UTF-8 ``application/x-www-form-urlencoded`` body."""

    if max_bytes <= 0 or max_fields <= 0:
        raise ValueError("form resource limits must be positive")
    if len(body) > max_bytes:
        raise FormDecodeError("form body is too large")
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise FormDecodeError("form body is not valid UTF-8") from error
    if _INVALID_PERCENT_ESCAPE.search(text):
        raise FormDecodeError("form body contains an invalid percent escape")
    if text and text.count("&") + 1 > max_fields:
        raise FormDecodeError("form contains too many fields")
    pairs = _parse_form_pairs(text, max_fields)
    return _unique_form_fields(pairs)


def _validate_password_parameters(salt: bytes | None, iterations: int) -> None:
    if salt is not None and len(salt) < _PASSWORD_SALT_BYTES:
        raise ValueError("password salt must be at least 16 bytes")
    if not _MIN_PASSWORD_ITERATIONS <= iterations <= _MAX_PASSWORD_ITERATIONS:
        raise ValueError("password iterations must be between 100000 and 1000000")


def _derive_password(password: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
        dklen=_PASSWORD_DIGEST_BYTES,
    )


def _parse_password_hash(encoded: str) -> tuple[int, bytes, bytes] | None:
    parts = encoded.split("$")
    if len(parts) != 4 or parts[0] != _HASH_SCHEME:
        return None
    try:
        iterations = int(parts[1])
        salt = _decode_base64url(parts[2])
        digest = _decode_base64url(parts[3])
    except (ValueError, binascii.Error):
        return None
    if not _MIN_PASSWORD_ITERATIONS <= iterations <= _MAX_PASSWORD_ITERATIONS:
        return None
    if len(salt) < _PASSWORD_SALT_BYTES or len(digest) != _PASSWORD_DIGEST_BYTES:
        return None
    return iterations, salt, digest


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


def _decode_session_claims(payload: bytes) -> SessionClaims | None:
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
    return SessionClaims(csrf_token, issued_at, expires_at)


def _is_safe_local_redirect(value: str) -> bool:
    decoded = unquote(value)
    if not value.startswith("/") or decoded.startswith("//"):
        return False
    if "\\" in decoded or any(
        ord(character) < 32 or ord(character) == 127 for character in decoded
    ):
        return False
    parts = urlsplit(value)
    return not parts.scheme and not parts.netloc and parts.path.startswith("/")


def _parse_form_pairs(text: str, max_fields: int) -> list[tuple[str, str]]:
    try:
        return parse_qsl(
            text,
            keep_blank_values=True,
            strict_parsing=True,
            encoding="utf-8",
            errors="strict",
            max_num_fields=max_fields,
        )
    except UnicodeDecodeError as error:
        raise FormDecodeError("form values are not valid UTF-8") from error
    except ValueError as error:
        raise FormDecodeError("form body is malformed") from error


def _unique_form_fields(pairs: list[tuple[str, str]]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for key, value in pairs:
        if key in fields:
            raise FormDecodeError(f"duplicate form field: {key}")
        fields[key] = value
    return fields


def _encode_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_base64url(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.b64decode(value + padding, altchars=b"-_", validate=True)


def _constant_time_bytes_equal(left: bytes, right: bytes) -> bool:
    return hmac.compare_digest(left, right)


def _constant_time_text_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left, right)
