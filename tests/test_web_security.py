"""Regression tests for dependency-free browser security primitives."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

import pytest

from agentboard.web.security import (
    FormDecodeError,
    SessionClaims,
    generate_csrf_token,
    hash_owner_password,
    normalize_local_redirect,
    parse_urlencoded_form,
    sign_session,
    verify_csrf_token,
    verify_owner_password,
    verify_session,
)

SALT = bytes.fromhex("00112233445566778899aabbccddeeff")
SECRET = "0123456789abcdef0123456789abcdef"


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _signed_payload(payload: object) -> str:
    raw_payload = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return _signed_raw_payload(raw_payload)


def _signed_raw_payload(raw_payload: bytes) -> str:
    signature = hmac.new(SECRET.encode(), raw_payload, hashlib.sha256).digest()
    return f"{_base64url(raw_payload)}.{_base64url(signature)}"


def test_password_hash_is_deterministic_with_a_fixed_salt_and_verifies() -> None:
    encoded = hash_owner_password("correct horse", salt=SALT, iterations=100_000)

    assert encoded == hash_owner_password(
        "correct horse",
        salt=SALT,
        iterations=100_000,
    )
    assert encoded.startswith("pbkdf2_sha256$100000$")
    assert verify_owner_password("correct horse", encoded) is True
    assert verify_owner_password("incorrect horse", encoded) is False


def test_password_verification_uses_constant_time_digest_comparison(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    encoded = hash_owner_password("owner password", salt=SALT, iterations=100_000)
    compared: list[tuple[bytes, bytes]] = []

    def compare_digest(left: bytes, right: bytes) -> bool:
        compared.append((left, right))
        return hmac.compare_digest(left, right)

    monkeypatch.setattr("agentboard.web.security._constant_time_bytes_equal", compare_digest)

    assert verify_owner_password("owner password", encoded) is True
    assert len(compared) == 1
    assert all(isinstance(value, bytes) for value in compared[0])


def test_password_hash_generates_a_cryptographic_salt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("agentboard.web.security.secrets.token_bytes", lambda size: b"x" * size)

    encoded = hash_owner_password("owner password", iterations=100_000)

    assert encoded.split("$")[2] == _base64url(b"x" * 16)


@pytest.mark.parametrize(
    "encoded",
    [
        "",
        "unknown$100000$AA$AA",
        "pbkdf2_sha256$not-a-number$AA$AA",
        "pbkdf2_sha256$99999$AA$AA",
        "pbkdf2_sha256$100000$not!base64$AA",
        f"pbkdf2_sha256$100000${_base64url(b'short')}${_base64url(b'x' * 32)}",
        f"pbkdf2_sha256$100000${_base64url(SALT)}${_base64url(b'short')}",
        "pbkdf2_sha256$100000$too$few$parts",
    ],
)
def test_password_verification_rejects_malformed_hashes(encoded: str) -> None:
    assert verify_owner_password("owner password", encoded) is False


def test_password_hash_rejects_unsafe_parameters() -> None:
    with pytest.raises(ValueError, match="at least 16 bytes"):
        hash_owner_password("owner password", salt=b"short")
    with pytest.raises(ValueError, match="between"):
        hash_owner_password("owner password", salt=SALT, iterations=99_999)
    with pytest.raises(ValueError, match="between"):
        hash_owner_password("owner password", salt=SALT, iterations=1_000_001)


def test_signed_session_round_trips_until_its_exact_expiry() -> None:
    token = sign_session(SECRET, csrf_token="csrf-value", now=1_000, ttl_seconds=60)

    assert verify_session(SECRET, token, now=1_059) == SessionClaims(
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


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "/projects"),
        ("", "/projects"),
        ("/projects/AB/backlog", "/projects/AB/backlog"),
        ("/projects/AB/board?focus=AB-1#ignored", "/projects/AB/board?focus=AB-1"),
        ("projects/AB", "/projects"),
        (" https://attacker.example", "/projects"),
        ("https://attacker.example", "/projects"),
        ("//attacker.example/path", "/projects"),
        ("///attacker.example/path", "/projects"),
        ("/%2f%2fattacker.example", "/projects"),
        (r"/\attacker.example", "/projects"),
        ("/%5cattacker.example", "/projects"),
        ("/safe%0d%0aLocation:%20https://attacker.example", "/projects"),
    ],
)
def test_redirect_normalization_allows_only_safe_local_targets(
    value: str | None,
    expected: str,
) -> None:
    assert normalize_local_redirect(value) == expected


def test_redirect_normalization_requires_a_safe_default() -> None:
    with pytest.raises(ValueError, match="safe local path"):
        normalize_local_redirect("/projects", default="https://attacker.example")


def test_urlencoded_form_parser_decodes_utf8_and_blank_values() -> None:
    body = b"password=caf%C3%A9+owner&next=%2Fprojects%2FAB&blank="

    assert parse_urlencoded_form(body) == {
        "password": "café owner",
        "next": "/projects/AB",
        "blank": "",
    }
    assert parse_urlencoded_form(b"") == {}


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (b"duplicate=one&duplicate=two", "duplicate"),
        (b"missing-equals", "malformed"),
        (b"value=%ZZ", "percent"),
        (b"value=%", "percent"),
        (b"\xff", "UTF-8"),
        (b"value=%FF", "UTF-8"),
    ],
)
def test_urlencoded_form_parser_rejects_ambiguous_or_malformed_input(
    body: bytes,
    message: str,
) -> None:
    with pytest.raises(FormDecodeError, match=message):
        parse_urlencoded_form(body)


def test_urlencoded_form_parser_enforces_resource_limits() -> None:
    with pytest.raises(FormDecodeError, match="too large"):
        parse_urlencoded_form(b"field=value", max_bytes=4)
    with pytest.raises(FormDecodeError, match="too many"):
        parse_urlencoded_form(b"a=1&b=2", max_fields=1)
    with pytest.raises(ValueError, match="positive"):
        parse_urlencoded_form(b"", max_bytes=0)
    with pytest.raises(ValueError, match="positive"):
        parse_urlencoded_form(b"", max_fields=0)
