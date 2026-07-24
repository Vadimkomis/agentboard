"""asyncio orchestrator — ticket dependency resolution and dispatch.

Manages the lifecycle of all engineering tickets within a story:
- Respects depends_on relationships
- Runs independent tickets in parallel
- Transitions story status when all tickets are done
- Handles partial failures gracefully
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from agentboard.core.db import get_session
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

logger = logging.getLogger(__name__)


class Orchestrator:
    """Manages async execution of all tickets within a story."""

    def __init__(
        self,
        engineering_runner: object,
        on_story_update: Callable[[int, StoryStatus], None] | None = None,
        on_ticket_update: Callable[[int, TicketStatus], None] | None = None,
    ) -> None:
        self._runner = engineering_runner
        self._on_story_update = on_story_update
        self._on_ticket_update = on_ticket_update
        # Active tasks by ticket_id
        self._active_tasks: dict[int, asyncio.Task] = {}

    async def decompose_and_start(
        self,
        story: Story,
        decomposed: object,  # DecomposedStory from pm_agent
        session: AsyncSession,
    ) -> None:
        """Create tickets from decomposition result and start execution.

        Called when user clicks Finalize (PM finalize).
        """
        from agentboard.agents.pm_agent import DecomposedStory

        assert isinstance(decomposed, DecomposedStory)

        # Create engineering tickets atomically
        created_tickets: list[Ticket] = []
        for idx, ticket_data in enumerate(decomposed.engineering_tickets):
            dependencies = ticket_data.get("depends_on") or [None]
            ticket = Ticket(
                story_id=story.id,
                ticket_index=idx,
                title=ticket_data.get("title", f"Ticket {idx}"),
                description=ticket_data.get("refined_description"),
                acceptance_criteria=ticket_data.get("acceptance_criteria"),
                prd_anchor=ticket_data.get("prd_anchor"),
                agent_type=AgentType(ticket_data.get("agent_type", "fullstack")),
                runtime=Runtime(ticket_data.get("runtime", "claude")),
                priority=ticket_data.get("priority", "medium"),
                complexity=ticket_data.get("complexity", "medium"),
                branch_name=ticket_data.get("branch_name"),
                context_files=json.dumps(ticket_data.get("context_files", [])),
                reasoning=ticket_data.get("reasoning"),
                depends_on_index=dependencies[0],
                status=TicketStatus.pending,
            )
            session.add(ticket)
            created_tickets.append(ticket)

        # Create marketing ticket if present
        if decomposed.marketing_ticket:
            mkt = decomposed.marketing_ticket
            marketing_ticket = Ticket(
                story_id=story.id,
                ticket_index=len(decomposed.engineering_tickets),
                title=mkt.get("title", "Write LAUNCH.md"),
                description=mkt.get("gtm_context"),
                prd_anchor=mkt.get("prd_anchor", "gtm"),
                agent_type=AgentType.marketing,
                runtime=Runtime.claude,
                status=TicketStatus.pending,
            )
            session.add(marketing_ticket)
            created_tickets.append(marketing_ticket)

        # Transition story to engineering
        story.status = StoryStatus.engineering
        story.last_activity_at = datetime.now(UTC)
        await session.flush()

        if self._on_story_update:
            self._on_story_update(story.id, StoryStatus.engineering)

        # Start execution of all tickets respecting dependencies
        asyncio.create_task(
            self._run_story_tickets(story.id, created_tickets),
            name=f"story-{story.id}-execution",
        )

    async def _run_story_tickets(
        self,
        story_id: int,
        tickets: list[Ticket],
    ) -> None:
        """Execute all tickets in dependency order, as parallel as possible."""
        completed: set[int] = set()
        failed: set[int] = set()

        # Index tickets by their ticket_index
        ticket_map = {t.ticket_index: t for t in tickets}
        pending = list(ticket_map.keys())

        while pending:
            # Find tickets that are ready to run (dependencies met)
            ready = [
                idx
                for idx in pending
                if ticket_map[idx].depends_on_index is None
                or ticket_map[idx].depends_on_index in completed
            ]

            if not ready:
                # All remaining tickets are blocked by failed deps
                logger.warning(
                    "Story %d: %d tickets blocked by failed dependencies", story_id, len(pending)
                )
                break

            # Start ready tickets in parallel
            tasks = {
                idx: asyncio.create_task(
                    self._execute_ticket(story_id, ticket_map[idx]),
                    name=f"ticket-{ticket_map[idx].id}",
                )
                for idx in ready
            }
            pending = [idx for idx in pending if idx not in ready]

            # Wait for all to complete
            results = await asyncio.gather(*tasks.values(), return_exceptions=True)

            for idx, result in zip(ready, results, strict=True):
                if isinstance(result, Exception):
                    logger.error("Ticket %d failed: %s", ticket_map[idx].id, result)
                    failed.add(idx)
                else:
                    completed.add(idx)

        # Check if story should transition to TESTING
        await self._check_story_completion(story_id)

    async def _execute_ticket(self, story_id: int, ticket: Ticket) -> None:
        """Execute a single ticket via the engineering runner."""
        async with get_session() as session:
            # Mark ticket as in_progress
            db_ticket = await session.get(Ticket, ticket.id)
            if db_ticket is None:
                raise RuntimeError(f"Ticket {ticket.id} not found")
            db_ticket.status = TicketStatus.in_progress
            db_ticket.started_at = datetime.now(UTC)
            await session.flush()

            if self._on_ticket_update:
                self._on_ticket_update(ticket.id, TicketStatus.in_progress)

            # Create execution record
            execution = Execution(
                ticket_id=ticket.id,
                runtime=ticket.runtime,
                status="running",
            )
            session.add(execution)
            await session.flush()

            # Get story for context
            story = await session.get(Story, story_id)
            if story is None:
                raise RuntimeError(f"Story {story_id} not found")

        # Run the engineering agent (outside transaction)
        log_buffer: list[str] = []

        def on_output(chunk: str) -> None:
            log_buffer.append(chunk)

        try:
            pr_url = await self._runner.run(  # type: ignore[call-arg]
                story=story,
                ticket=ticket,
                execution=execution,
                on_output=on_output,
            )

            # Save logs and mark done
            async with get_session() as session:
                # Flush logs to DB
                if log_buffer:
                    log = ExecutionLog(
                        execution_id=execution.id,
                        log_type="stdout",
                        content="".join(log_buffer),
                    )
                    session.add(log)

                db_execution = await session.get(Execution, execution.id)
                if db_execution:
                    db_execution.status = "done"
                    db_execution.completed_at = datetime.now(UTC)

                db_ticket = await session.get(Ticket, ticket.id)
                if db_ticket:
                    db_ticket.status = TicketStatus.done
                    db_ticket.pr_url = pr_url
                    db_ticket.completed_at = datetime.now(UTC)

            if self._on_ticket_update:
                self._on_ticket_update(ticket.id, TicketStatus.done)

        except Exception as e:
            async with get_session() as session:
                if log_buffer:
                    log = ExecutionLog(
                        execution_id=execution.id,
                        log_type="stderr",
                        content="".join(log_buffer) + f"\nFATAL: {e}",
                    )
                    session.add(log)

                db_execution = await session.get(Execution, execution.id)
                if db_execution:
                    db_execution.status = "failed"
                    db_execution.error_message = str(e)
                    db_execution.completed_at = datetime.now(UTC)

                db_ticket = await session.get(Ticket, ticket.id)
                if db_ticket:
                    db_ticket.status = TicketStatus.failed
                    db_ticket.completed_at = datetime.now(UTC)

            if self._on_ticket_update:
                self._on_ticket_update(ticket.id, TicketStatus.failed)
            raise

    async def _check_story_completion(self, story_id: int) -> None:
        """Transition story to TESTING if all tickets are terminal."""
        async with get_session() as session:
            story = await session.get(Story, story_id)
            if story is None:
                return

            # Refresh tickets
            await session.refresh(story, ["tickets"])
            all_terminal = all(t.is_terminal for t in story.tickets)

            if all_terminal:
                story.status = StoryStatus.testing
                story.last_activity_at = datetime.now(UTC)
                if self._on_story_update:
                    self._on_story_update(story_id, StoryStatus.testing)
