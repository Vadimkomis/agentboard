"""Tests for the async SQLite lifecycle and transaction boundary."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentboard.core import db
from agentboard.core.models import Story, StoryStatus


@pytest.fixture(autouse=True)
async def reset_database_state():
    await db.close_db()
    db._session_factory = None
    yield
    await db.close_db()
    db._session_factory = None


def test_get_db_url_uses_explicit_and_default_paths(monkeypatch, tmp_path):
    explicit = tmp_path / "explicit.db"
    assert db.get_db_url(explicit) == f"sqlite+aiosqlite:///{explicit}"

    default = tmp_path / "default.db"
    monkeypatch.setattr(db, "DEFAULT_DB_PATH", default)
    assert db.get_db_url() == f"sqlite+aiosqlite:///{default}"


async def test_init_session_commit_and_close(tmp_path):
    database = tmp_path / "nested" / "agentboard.db"
    await db.init_db(database)
    assert database.parent.exists()
    assert db.get_engine() is not None

    async with db.get_session() as session:
        session.add(Story(title="Persisted", status=StoryStatus.drafting))

    async with db.get_session() as session:
        story = await session.get(Story, 1)
        assert story is not None
        assert story.title == "Persisted"

    await db.close_db()
    assert db._engine is None


async def test_session_rolls_back_on_error(tmp_path):
    await db.init_db(tmp_path / "rollback.db")

    with pytest.raises(RuntimeError, match="boom"):
        async with db.get_session() as session:
            session.add(Story(title="Rolled back", status=StoryStatus.drafting))
            await session.flush()
            raise RuntimeError("boom")

    async with db.get_session() as session:
        assert await session.get(Story, 1) is None


async def test_uninitialized_accessors_raise():
    db._engine = None
    db._session_factory = None

    with pytest.raises(RuntimeError, match="Database not initialized"):
        db.get_engine()
    with pytest.raises(RuntimeError, match="Database not initialized"):
        async with db.get_session():
            pass


def test_default_database_path_is_a_path():
    assert isinstance(db.DEFAULT_DB_PATH, Path)
