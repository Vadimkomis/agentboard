"""Translate expected SQLite write conflicts into typed domain failures."""

from __future__ import annotations

from typing import NoReturn

from sqlalchemy.exc import IntegrityError, OperationalError

from agentboard.domain.errors import PersistenceConflictError


def raise_write_conflict(error: IntegrityError | OperationalError) -> NoReturn:
    if isinstance(error, IntegrityError) or _is_busy(error):
        raise PersistenceConflictError from error
    raise error


def _is_busy(error: OperationalError) -> bool:
    message = str(error.orig).casefold()
    return "locked" in message or "busy" in message
