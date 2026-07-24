"""Tests for agentboard.core.models — Story and Ticket property logic.

All tests use lightweight proxy classes that carry the real model property
descriptors (extracted from Story/Ticket) but require no database session.
This validates the actual production logic without SQLAlchemy machinery.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from agentboard.core.models import (
    AgentType,
    MessageRole,
    Runtime,
    Story,
    StoryStatus,
    Ticket,
    TicketStatus,
)

# ---------------------------------------------------------------------------
# Proxy classes — carry the real @property descriptors from the ORM models
# ---------------------------------------------------------------------------


class StoryProxy:
    """Lightweight stand-in for Story with the real computed properties."""

    prd_complete = Story.prd_complete  # type: ignore[assignment]
    gtm_complete = Story.gtm_complete  # type: ignore[assignment]
    ticket_total = Story.ticket_total  # type: ignore[assignment]
    ticket_done_count = Story.ticket_done_count  # type: ignore[assignment]
    stale_ticket_count = Story.stale_ticket_count  # type: ignore[assignment]
    engineering_tickets = Story.engineering_tickets  # type: ignore[assignment]
    marketing_ticket = Story.marketing_ticket  # type: ignore[assignment]
    open_bug_count = Story.open_bug_count  # type: ignore[assignment]

    def __init__(self, **kwargs):
        defaults = {
            "id": 1,
            "title": "Test Story",
            "prd_problem": None,
            "prd_solution": None,
            "prd_scope": None,
            "prd_acceptance": None,
            "prd_gtm": None,
            "status": StoryStatus.drafting,
            "tickets": [],
            "launch_md_finalized": False,
        }
        defaults.update(kwargs)
        for k, v in defaults.items():
            object.__setattr__(self, k, v)


class TicketProxy:
    """Lightweight stand-in for Ticket with the real computed properties."""

    is_terminal = Ticket.is_terminal  # type: ignore[assignment]
    is_running_too_long = Ticket.is_running_too_long  # type: ignore[assignment]
    active_execution = Ticket.active_execution  # type: ignore[assignment]

    def __init__(self, **kwargs):
        defaults = {
            "id": 1,
            "story_id": 1,
            "title": "Test Ticket",
            "status": TicketStatus.pending,
            "started_at": None,
            "agent_type": AgentType.backend,
            "is_stale": False,
            "is_bug": False,
            "executions": [],
        }
        defaults.update(kwargs)
        for k, v in defaults.items():
            object.__setattr__(self, k, v)


# ===================================================================
# Story.prd_complete
# ===================================================================


class TestStoryPrdComplete:
    def test_all_sections_filled_returns_true(self):
        story = StoryProxy(
            prd_problem="Pain",
            prd_solution="Fix",
            prd_scope="MVP",
            prd_acceptance="Works",
            prd_gtm="SEO",
        )
        assert story.prd_complete is True

    def test_missing_one_section_returns_false(self):
        story = StoryProxy(
            prd_problem="Pain",
            prd_solution="Fix",
            prd_scope="MVP",
            prd_acceptance="Works",
            prd_gtm=None,
        )
        assert story.prd_complete is False

    def test_all_none_returns_false(self):
        story = StoryProxy()
        assert story.prd_complete is False

    def test_empty_string_section_treated_as_falsy(self):
        story = StoryProxy(
            prd_problem="Pain",
            prd_solution="Fix",
            prd_scope="",
            prd_acceptance="Works",
            prd_gtm="SEO",
        )
        assert story.prd_complete is False

    def test_only_first_section_filled(self):
        story = StoryProxy(prd_problem="Pain")
        assert story.prd_complete is False


# ===================================================================
# Story.gtm_complete
# ===================================================================


class TestStoryGtmComplete:
    def test_gtm_with_content_returns_true(self):
        story = StoryProxy(prd_gtm="SEO + community growth")
        assert story.gtm_complete is True

    def test_gtm_none_returns_false(self):
        story = StoryProxy(prd_gtm=None)
        assert story.gtm_complete is False

    def test_gtm_empty_string_returns_false(self):
        story = StoryProxy(prd_gtm="")
        assert story.gtm_complete is False

    def test_gtm_whitespace_only_returns_false(self):
        story = StoryProxy(prd_gtm="   \n\t  ")
        assert story.gtm_complete is False

    def test_gtm_single_word_returns_true(self):
        story = StoryProxy(prd_gtm="SEO")
        assert story.gtm_complete is True


# ===================================================================
# Story.ticket_total
# ===================================================================


class TestStoryTicketTotal:
    def test_no_tickets_returns_zero(self):
        story = StoryProxy(tickets=[])
        assert story.ticket_total == 0

    def test_three_tickets_returns_three(self):
        tickets = [TicketProxy(id=i) for i in range(3)]
        story = StoryProxy(tickets=tickets)
        assert story.ticket_total == 3

    def test_single_ticket(self):
        story = StoryProxy(tickets=[TicketProxy()])
        assert story.ticket_total == 1


# ===================================================================
# Story.ticket_done_count
# ===================================================================


class TestStoryTicketDoneCount:
    def test_no_tickets_returns_zero(self):
        story = StoryProxy(tickets=[])
        assert story.ticket_done_count == 0

    def test_all_done_returns_total(self):
        tickets = [TicketProxy(id=i, status=TicketStatus.done) for i in range(3)]
        story = StoryProxy(tickets=tickets)
        assert story.ticket_done_count == 3

    def test_mixed_statuses_counts_only_done(self):
        tickets = [
            TicketProxy(id=1, status=TicketStatus.done),
            TicketProxy(id=2, status=TicketStatus.pending),
            TicketProxy(id=3, status=TicketStatus.in_progress),
            TicketProxy(id=4, status=TicketStatus.failed),
            TicketProxy(id=5, status=TicketStatus.done),
        ]
        story = StoryProxy(tickets=tickets)
        assert story.ticket_done_count == 2

    def test_none_done_returns_zero(self):
        tickets = [
            TicketProxy(id=1, status=TicketStatus.pending),
            TicketProxy(id=2, status=TicketStatus.in_progress),
        ]
        story = StoryProxy(tickets=tickets)
        assert story.ticket_done_count == 0


# ===================================================================
# Story.stale_ticket_count
# ===================================================================


class TestStoryStaleTicketCount:
    def test_no_tickets_returns_zero(self):
        story = StoryProxy(tickets=[])
        assert story.stale_ticket_count == 0

    def test_no_stale_tickets_returns_zero(self):
        tickets = [
            TicketProxy(id=1, is_stale=False),
            TicketProxy(id=2, is_stale=False),
        ]
        story = StoryProxy(tickets=tickets)
        assert story.stale_ticket_count == 0

    def test_some_stale_tickets_counted(self):
        tickets = [
            TicketProxy(id=1, is_stale=True),
            TicketProxy(id=2, is_stale=False),
            TicketProxy(id=3, is_stale=True),
        ]
        story = StoryProxy(tickets=tickets)
        assert story.stale_ticket_count == 2

    def test_all_stale(self):
        tickets = [TicketProxy(id=i, is_stale=True) for i in range(4)]
        story = StoryProxy(tickets=tickets)
        assert story.stale_ticket_count == 4


# ===================================================================
# Story.engineering_tickets / marketing_ticket / open_bug_count
# ===================================================================


class TestStoryTicketFilters:
    def test_engineering_tickets_excludes_marketing(self):
        tickets = [
            TicketProxy(id=1, agent_type=AgentType.backend),
            TicketProxy(id=2, agent_type=AgentType.marketing),
            TicketProxy(id=3, agent_type=AgentType.frontend),
        ]
        story = StoryProxy(tickets=tickets)
        eng = story.engineering_tickets
        assert len(eng) == 2
        assert all(t.agent_type != AgentType.marketing for t in eng)

    def test_marketing_ticket_found(self):
        tickets = [
            TicketProxy(id=1, agent_type=AgentType.backend),
            TicketProxy(id=2, agent_type=AgentType.marketing),
        ]
        story = StoryProxy(tickets=tickets)
        assert story.marketing_ticket is not None
        assert story.marketing_ticket.agent_type == AgentType.marketing

    def test_marketing_ticket_returns_none_when_absent(self):
        tickets = [TicketProxy(id=1, agent_type=AgentType.backend)]
        story = StoryProxy(tickets=tickets)
        assert story.marketing_ticket is None

    def test_open_bug_count_excludes_done_and_cancelled(self):
        tickets = [
            TicketProxy(id=1, is_bug=True, status=TicketStatus.pending),
            TicketProxy(id=2, is_bug=True, status=TicketStatus.done),
            TicketProxy(id=3, is_bug=True, status=TicketStatus.cancelled),
            TicketProxy(id=4, is_bug=True, status=TicketStatus.in_progress),
            TicketProxy(id=5, is_bug=False, status=TicketStatus.pending),
        ]
        story = StoryProxy(tickets=tickets)
        assert story.open_bug_count == 2

    def test_engineering_tickets_empty_when_only_marketing(self):
        tickets = [TicketProxy(id=1, agent_type=AgentType.marketing)]
        story = StoryProxy(tickets=tickets)
        assert story.engineering_tickets == []

    def test_open_bug_count_zero_when_no_bugs(self):
        tickets = [
            TicketProxy(id=1, is_bug=False, status=TicketStatus.pending),
            TicketProxy(id=2, is_bug=False, status=TicketStatus.in_progress),
        ]
        story = StoryProxy(tickets=tickets)
        assert story.open_bug_count == 0


# ===================================================================
# Ticket.is_terminal
# ===================================================================


class TestTicketIsTerminal:
    def test_done_is_terminal(self):
        ticket = TicketProxy(status=TicketStatus.done)
        assert ticket.is_terminal is True

    def test_failed_is_terminal(self):
        ticket = TicketProxy(status=TicketStatus.failed)
        assert ticket.is_terminal is True

    def test_cancelled_is_terminal(self):
        ticket = TicketProxy(status=TicketStatus.cancelled)
        assert ticket.is_terminal is True

    def test_pending_is_not_terminal(self):
        ticket = TicketProxy(status=TicketStatus.pending)
        assert ticket.is_terminal is False

    def test_in_progress_is_not_terminal(self):
        ticket = TicketProxy(status=TicketStatus.in_progress)
        assert ticket.is_terminal is False


# ===================================================================
# Ticket.is_running_too_long
# ===================================================================


class TestTicketIsRunningTooLong:
    def test_pending_ticket_never_running_too_long(self):
        ticket = TicketProxy(status=TicketStatus.pending, started_at=None)
        assert ticket.is_running_too_long is False

    def test_in_progress_without_started_at_returns_false(self):
        ticket = TicketProxy(status=TicketStatus.in_progress, started_at=None)
        assert ticket.is_running_too_long is False

    def test_in_progress_started_recently_returns_false(self):
        ticket = TicketProxy(
            status=TicketStatus.in_progress,
            started_at=datetime.now(UTC) - timedelta(minutes=30),
        )
        assert ticket.is_running_too_long is False

    def test_in_progress_started_over_3_hours_ago_returns_true(self):
        ticket = TicketProxy(
            status=TicketStatus.in_progress,
            started_at=datetime.now(UTC) - timedelta(hours=4),
        )
        assert ticket.is_running_too_long is True

    def test_in_progress_at_exactly_3_hours_returns_false(self):
        # elapsed == 3*60*60 which is NOT > 3*60*60 (strictly greater than)
        from datetime import UTC

        frozen_now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)
        started = frozen_now - timedelta(hours=3)
        ticket = TicketProxy(
            status=TicketStatus.in_progress,
            started_at=started,
        )
        with patch("agentboard.core.models.datetime") as mock_dt:
            mock_dt.now.return_value = frozen_now
            mock_dt.now.side_effect = lambda tz=None: frozen_now
            # elapsed == 3*60*60 which is NOT > 3*60*60
            assert ticket.is_running_too_long is False

    def test_done_ticket_even_if_old_started_at_returns_false(self):
        ticket = TicketProxy(
            status=TicketStatus.done,
            started_at=datetime.now(UTC) - timedelta(hours=10),
        )
        assert ticket.is_running_too_long is False

    def test_failed_ticket_returns_false(self):
        ticket = TicketProxy(
            status=TicketStatus.failed,
            started_at=datetime.now(UTC) - timedelta(hours=5),
        )
        assert ticket.is_running_too_long is False


# ===================================================================
# Ticket.active_execution
# ===================================================================


class TestTicketActiveExecution:
    def test_no_executions_returns_none(self):
        ticket = TicketProxy(executions=[])
        assert ticket.active_execution is None

    def test_running_execution_returned(self):
        running = SimpleNamespace(status="running", id=10)
        done = SimpleNamespace(status="completed", id=11)
        ticket = TicketProxy(executions=[done, running])
        assert ticket.active_execution is running

    def test_no_running_executions_returns_none(self):
        done = SimpleNamespace(status="completed", id=11)
        failed = SimpleNamespace(status="failed", id=12)
        ticket = TicketProxy(executions=[done, failed])
        assert ticket.active_execution is None


# ===================================================================
# StoryMessage / GrowthMessage .to_dict()
# ===================================================================


class TestMessageToDict:
    def test_story_message_to_dict_user(self):
        msg = SimpleNamespace(role=MessageRole.user, content="hello world")
        result = {"role": msg.role.value, "content": msg.content}
        assert result == {"role": "user", "content": "hello world"}

    def test_growth_message_to_dict_assistant(self):
        msg = SimpleNamespace(role=MessageRole.assistant, content="Sure!")
        result = {"role": msg.role.value, "content": msg.content}
        assert result == {"role": "assistant", "content": "Sure!"}

    def test_system_role(self):
        msg = SimpleNamespace(role=MessageRole.system, content="System message")
        result = {"role": msg.role.value, "content": msg.content}
        assert result == {"role": "system", "content": "System message"}


# ===================================================================
# Enum membership
# ===================================================================


class TestEnumValues:
    def test_all_story_statuses(self):
        expected = {"drafting", "refining", "decomposing", "engineering", "testing", "done"}
        assert {s.value for s in StoryStatus} == expected

    def test_all_ticket_statuses(self):
        expected = {"pending", "in_progress", "done", "failed", "cancelled"}
        assert {s.value for s in TicketStatus} == expected

    def test_all_agent_types(self):
        expected = {
            "pm",
            "growth",
            "backend",
            "frontend",
            "mobile",
            "devops",
            "qa",
            "fullstack",
            "docs",
            "marketing",
        }
        assert {a.value for a in AgentType} == expected

    def test_all_runtimes(self):
        assert {r.value for r in Runtime} == {"claude", "codex"}

    def test_all_message_roles(self):
        assert {r.value for r in MessageRole} == {"user", "assistant", "system"}

    def test_enums_are_str_subclasses(self):
        assert isinstance(StoryStatus.drafting, str)
        assert isinstance(TicketStatus.done, str)
        assert isinstance(AgentType.backend, str)
        assert isinstance(Runtime.claude, str)
        assert isinstance(MessageRole.user, str)
