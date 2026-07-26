"""Small shared helpers for application handlers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import TypeAlias

from agentboard.domain.errors import InvalidInputError

Clock: TypeAlias = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


def require_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise InvalidInputError(f"{field_name} must not be empty.")
    return normalized


def persisted_id(identifier: int | None) -> int:
    if identifier is None:
        raise RuntimeError("The persistence adapter did not assign an identifier.")
    return identifier
