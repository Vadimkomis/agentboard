"""Integration-style tests for ticket dispatch and lifecycle persistence."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy import select

from agentboard.agents.pm_agent import DecomposedStory
from agentboard.core import db
from agentboard.core.models import (
    AgentType,
    Execution,
    ExecutionLog,
    Runtime,
    Story,
    StoryStatus,
    Ticket,
    TicketStatus,
)
from agentboard.workers.orchestrator import Orchestrator


@pytest.fixture
async def orchestrator_database(tmp_path):
    await db.close_db()
    db._session_factory = None
    await db.init_db(tmp_path / "orchestrator.db")
    async with db.get_session() as session:
        story = Story(title="Feature", status=StoryStatus.drafting)
        session.add(story)
        await session.flush()
        story_id = story.id
    yield story_id
    await db.close_db()
    db._session_factory = None


async def _add_ticket(story_id, **overrides):
    values = {
        "story_id": story_id,
        "title": "Task",
        "agent_type": AgentType.backend,
        "runtime": Runtime.claude,
        "status": TicketStatus.pending,
        "ticket_index": 0,
    }
    values.update(overrides)
    async with db.get_session() as session:
        ticket = Ticket(**values)
        session.add(ticket)
        await session.flush()
        return ticket.id


async def test_decompose_creates_tickets_and_starts_background_run(orchestrator_database):
    story_updates = Mock()
    orchestrator = Orchestrator(Mock(), on_story_update=story_updates)
    decomposed = DecomposedStory(
        engineering_tickets=[
            {
                "title": "API",
                "agent_type": "backend",
                "runtime": "codex",
                "context_files": ["api.py"],
                "depends_on": [],
            }
        ],
        marketing_ticket={"title": "Launch", "gtm_context": "Plan"},
    )
    captured = []

    def capture(coro, *, name):
        captured.append((coro, name))
        return Mock()

    async with db.get_session() as session:
        story = await session.get(Story, orchestrator_database)
        with patch("agentboard.workers.orchestrator.asyncio.create_task", side_effect=capture):
            await orchestrator.decompose_and_start(story, decomposed, session)
        result = await session.execute(select(Ticket).order_by(Ticket.ticket_index))
        tickets = list(result.scalars())
        assert [ticket.title for ticket in tickets] == ["API", "Launch"]
        assert tickets[0].runtime == Runtime.codex
        assert tickets[0].context_files == '["api.py"]'
        assert story.status == StoryStatus.engineering

    story_updates.assert_called_once_with(orchestrator_database, StoryStatus.engineering)
    assert captured[0][1] == f"story-{orchestrator_database}-execution"
    captured[0][0].close()


async def test_run_story_tickets_respects_dependencies_and_records_failures():
    orchestrator = Orchestrator(Mock())
    first = SimpleNamespace(id=1, ticket_index=0, depends_on_index=None)
    second = SimpleNamespace(id=2, ticket_index=1, depends_on_index=0)
    orchestrator._execute_ticket = AsyncMock(side_effect=[None, RuntimeError("second failed")])
    orchestrator._check_story_completion = AsyncMock()

    await orchestrator._run_story_tickets(8, [first, second])

    assert orchestrator._execute_ticket.await_count == 2
    orchestrator._check_story_completion.assert_awaited_once_with(8)


async def test_run_story_tickets_stops_when_dependencies_are_blocked():
    orchestrator = Orchestrator(Mock())
    blocked = SimpleNamespace(id=2, ticket_index=1, depends_on_index=99)
    orchestrator._execute_ticket = AsyncMock()
    orchestrator._check_story_completion = AsyncMock()

    await orchestrator._run_story_tickets(8, [blocked])

    orchestrator._execute_ticket.assert_not_awaited()
    orchestrator._check_story_completion.assert_awaited_once_with(8)


async def test_execute_ticket_success_persists_output(orchestrator_database):
    ticket_id = await _add_ticket(orchestrator_database)
    runner = Mock()

    async def run(**kwargs):
        kwargs["on_output"]("hello ")
        kwargs["on_output"]("world")
        return "https://github.test/pr/1"

    runner.run = run
    updates = Mock()
    orchestrator = Orchestrator(runner, on_ticket_update=updates)
    async with db.get_session() as session:
        ticket = await session.get(Ticket, ticket_id)

    await orchestrator._execute_ticket(orchestrator_database, ticket)

    async with db.get_session() as session:
        ticket = await session.get(Ticket, ticket_id)
        execution = (await session.execute(select(Execution))).scalar_one()
        log = (await session.execute(select(ExecutionLog))).scalar_one()
        assert ticket.status == TicketStatus.done
        assert ticket.pr_url.endswith("/1")
        assert execution.status == "done"
        assert log.content == "hello world"
    assert [call.args[1] for call in updates.call_args_list] == [
        TicketStatus.in_progress,
        TicketStatus.done,
    ]


async def test_execute_ticket_failure_persists_error(orchestrator_database):
    ticket_id = await _add_ticket(orchestrator_database)
    runner = Mock()

    async def run(**kwargs):
        kwargs["on_output"]("partial")
        raise RuntimeError("agent crashed")

    runner.run = run
    updates = Mock()
    orchestrator = Orchestrator(runner, on_ticket_update=updates)
    async with db.get_session() as session:
        ticket = await session.get(Ticket, ticket_id)

    with pytest.raises(RuntimeError, match="agent crashed"):
        await orchestrator._execute_ticket(orchestrator_database, ticket)

    async with db.get_session() as session:
        ticket = await session.get(Ticket, ticket_id)
        execution = (await session.execute(select(Execution))).scalar_one()
        log = (await session.execute(select(ExecutionLog))).scalar_one()
        assert ticket.status == TicketStatus.failed
        assert execution.status == "failed"
        assert execution.error_message == "agent crashed"
        assert "FATAL: agent crashed" in log.content
    assert updates.call_args_list[-1].args[1] == TicketStatus.failed


async def test_execute_ticket_rejects_missing_ticket(orchestrator_database):
    fake = SimpleNamespace(id=999, runtime=Runtime.claude)
    with pytest.raises(RuntimeError, match="Ticket 999 not found"):
        await Orchestrator(Mock())._execute_ticket(orchestrator_database, fake)


async def test_execute_ticket_rejects_missing_story(orchestrator_database):
    ticket_id = await _add_ticket(orchestrator_database)
    async with db.get_session() as session:
        ticket = await session.get(Ticket, ticket_id)
    with pytest.raises(RuntimeError, match="Story 999 not found"):
        await Orchestrator(Mock())._execute_ticket(999, ticket)


async def test_check_story_completion_missing_incomplete_and_complete(
    orchestrator_database,
):
    updates = Mock()
    orchestrator = Orchestrator(Mock(), on_story_update=updates)
    await orchestrator._check_story_completion(999)

    ticket_id = await _add_ticket(orchestrator_database)
    await orchestrator._check_story_completion(orchestrator_database)
    updates.assert_not_called()

    async with db.get_session() as session:
        ticket = await session.get(Ticket, ticket_id)
        ticket.status = TicketStatus.done

    await orchestrator._check_story_completion(orchestrator_database)
    async with db.get_session() as session:
        story = await session.get(Story, orchestrator_database)
        assert story.status == StoryStatus.testing
    updates.assert_called_once_with(orchestrator_database, StoryStatus.testing)
