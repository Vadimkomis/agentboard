"""Shared test fixtures for agentboard tests."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from agentboard.core.models import (
    AgentType,
    MessageRole,
    Runtime,
    StoryStatus,
    TicketStatus,
)


def _make_story(**overrides):
    """Build a lightweight Story-like object without touching the DB.

    Uses SimpleNamespace so we can set arbitrary attributes and still
    access them via dot notation, exactly like the real ORM model.
    """
    defaults = {
        "id": 1,
        "title": "Test Story",
        "prd_problem": None,
        "prd_solution": None,
        "prd_scope": None,
        "prd_acceptance": None,
        "prd_gtm": None,
        "status": StoryStatus.drafting,
        "repo_url": None,
        "repo_branch": None,
        "launch_md_pr_url": None,
        "launch_md_finalized": False,
        "created_at": datetime(2026, 1, 1),
        "updated_at": datetime(2026, 1, 1),
        "last_activity_at": datetime(2026, 1, 1),
        "archived_at": None,
        "pm_messages": [],
        "growth_messages": [],
        "tickets": [],
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_ticket(**overrides):
    """Build a lightweight Ticket-like object without touching the DB."""
    defaults = {
        "id": 1,
        "story_id": 1,
        "title": "Test Ticket",
        "description": "Do something",
        "acceptance_criteria": None,
        "prd_anchor": None,
        "is_stale": False,
        "agent_type": AgentType.backend,
        "runtime": Runtime.claude,
        "priority": "medium",
        "complexity": "medium",
        "status": TicketStatus.pending,
        "branch_name": None,
        "pr_url": None,
        "context_files": None,
        "reasoning": None,
        "depends_on_index": None,
        "ticket_index": 0,
        "is_bug": False,
        "bug_description": None,
        "created_at": datetime(2026, 1, 1),
        "updated_at": datetime(2026, 1, 1),
        "started_at": None,
        "completed_at": None,
        "executions": [],
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_story_message(role="user", content="hello"):
    return SimpleNamespace(
        role=MessageRole(role),
        content=content,
    )


def _make_growth_message(role="user", content="hello"):
    msg = SimpleNamespace(
        role=MessageRole(role),
        content=content,
    )
    msg.to_dict = lambda: {"role": msg.role.value, "content": msg.content}
    return msg


@pytest.fixture
def make_story():
    return _make_story


@pytest.fixture
def make_ticket():
    return _make_ticket


@pytest.fixture
def make_story_message():
    return _make_story_message


@pytest.fixture
def make_growth_message():
    return _make_growth_message
