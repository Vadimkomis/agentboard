"""Regression tests for dependency-free browser security primitives."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

import pytest

from agentboard.web.security import (
    CsrfSession,
    generate_csrf_token,
    sign_session,
    verify_csrf_token,
    verify_session,
)

SECRET = "0123456789abcdef0123456789abcdef"


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _signed_payload(payload: object) -> str:
    raw_payload = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return _signed_raw_payload(raw_payload)


def _signed_raw_payload(raw_payload: bytes) -> str:
    signature = hmac.new(SECRET.encode(), raw_payload, hashlib.sha256).digest()
    return f"{_base64url(raw_payload)}.{_base64url(signature)}"


def test_signed_session_round_trips_until_its_exact_expiry() -> None:
    token = sign_session(SECRET, csrf_token="csrf-value", now=1_000, ttl_seconds=60)

    assert verify_session(SECRET, token, now=1_059) == CsrfSession(
        csrf_token="csrf-value",
        issued_at=1_000,
        expires_at=1_060,
    )
    assert verify_session(SECRET, token, now=1_060) is None


def test_signed_session_rejects_tampering_and_wrong_secrets() -> None:
    token = sign_session(SECRET, csrf_token="csrf-value", now=1_000)
    payload, signature = token.split(".")
    tampered_payload = ("A" if payload[0] != "A" else "B") + payload[1:]
    tampered_signature = ("A" if signature[0] != "A" else "B") + signature[1:]

    assert verify_session(SECRET, f"{tampered_payload}.{signature}", now=1_001) is None
    assert verify_session(SECRET, f"{payload}.{tampered_signature}", now=1_001) is None
    assert verify_session(SECRET, f"{payload}.{_base64url(b'short')}", now=1_001) is None
    assert verify_session("fedcba9876543210fedcba9876543210", token, now=1_001) is None


@pytest.mark.parametrize(
    "token",
    [
        None,
        "",
        "one-part",
        "too.many.parts",
        "not!base64.still-not!base64",
        _signed_raw_payload(b"not-json"),
        _signed_payload({"csrf": "token", "iat": 1_000}),
        _signed_payload({"csrf": "", "exp": 1_100, "iat": 1_000}),
        _signed_payload({"csrf": "token", "exp": True, "iat": 1_000}),
        _signed_payload({"csrf": "token", "exp": 999, "iat": 1_000}),
        _signed_payload(["csrf", 1_000, 1_100]),
    ],
)
def test_signed_session_rejects_malformed_claims(token: str | None) -> None:
    assert verify_session(SECRET, token, now=1_001) is None


def test_signed_session_rejects_unsafe_inputs() -> None:
    with pytest.raises(ValueError, match="at least 32 bytes"):
        sign_session("short", csrf_token="token", now=1_000)
    with pytest.raises(ValueError, match="must not be empty"):
        sign_session(SECRET, csrf_token="", now=1_000)
    with pytest.raises(ValueError, match="positive"):
        sign_session(SECRET, csrf_token="token", now=1_000, ttl_seconds=0)
    with pytest.raises(ValueError, match="at least 32 bytes"):
        verify_session("short", "cookie", now=1_000)


def test_csrf_tokens_are_generated_and_compared_in_constant_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "agentboard.web.security.secrets.token_urlsafe",
        lambda size: f"generated-{size}",
    )
    comparisons: list[tuple[str, str]] = []

    def compare_digest(left: str, right: str) -> bool:
        comparisons.append((left, right))
        return hmac.compare_digest(left, right)

    monkeypatch.setattr("agentboard.web.security._constant_time_text_equal", compare_digest)

    assert generate_csrf_token() == "generated-32"
    assert verify_csrf_token("expected", "expected") is True
    assert verify_csrf_token("expected", "different") is False
    assert verify_csrf_token("expected", None) is False
    assert comparisons == [("expected", "expected"), ("expected", "different")]


def test_csrf_comparison_accepts_an_authentic_token() -> None:
    assert verify_csrf_token("authentic", "authentic") is True
