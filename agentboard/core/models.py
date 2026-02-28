"""SQLAlchemy ORM models for AgentBoard."""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class StoryStatus(str, enum.Enum):
    drafting = "drafting"
    refining = "refining"
    decomposing = "decomposing"
    engineering = "engineering"
    testing = "testing"
    done = "done"


class TicketStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"


class AgentType(str, enum.Enum):
    pm = "pm"
    growth = "growth"
    backend = "backend"
    frontend = "frontend"
    mobile = "mobile"
    devops = "devops"
    qa = "qa"
    fullstack = "fullstack"
    docs = "docs"
    marketing = "marketing"


class Runtime(str, enum.Enum):
    claude = "claude"
    codex = "codex"


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


# ---------------------------------------------------------------------------
# Story (top-level unit of work, lives on the Kanban board)
# ---------------------------------------------------------------------------


class Story(Base):
    __tablename__ = "stories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)

    # PRD sections
    prd_problem: Mapped[str | None] = mapped_column(Text, nullable=True)
    prd_solution: Mapped[str | None] = mapped_column(Text, nullable=True)
    prd_scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    prd_acceptance: Mapped[str | None] = mapped_column(Text, nullable=True)
    prd_gtm: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[StoryStatus] = mapped_column(
        Enum(StoryStatus), default=StoryStatus.drafting, nullable=False
    )

    # Repo info
    repo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    repo_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Launch artifact
    launch_md_pr_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    launch_md_finalized: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Future: embedding for semantic search (pgvector placeholder for SQLite)
    # embedding: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    pm_messages: Mapped[list[StoryMessage]] = relationship(
        "StoryMessage", back_populates="story", cascade="all, delete-orphan",
        foreign_keys="StoryMessage.story_id"
    )
    growth_messages: Mapped[list[GrowthMessage]] = relationship(
        "GrowthMessage", back_populates="story", cascade="all, delete-orphan"
    )
    tickets: Mapped[list[Ticket]] = relationship(
        "Ticket", back_populates="story", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Story id={self.id} title={self.title!r} status={self.status}>"

    @property
    def prd_complete(self) -> bool:
        """True if all 5 PRD sections have content."""
        return all([
            self.prd_problem,
            self.prd_solution,
            self.prd_scope,
            self.prd_acceptance,
            self.prd_gtm,
        ])

    @property
    def gtm_complete(self) -> bool:
        """True if GTM section has content."""
        return bool(self.prd_gtm and self.prd_gtm.strip())

    @property
    def ticket_total(self) -> int:
        return len(self.tickets)

    @property
    def ticket_done_count(self) -> int:
        return sum(1 for t in self.tickets if t.status == TicketStatus.done)

    @property
    def engineering_tickets(self) -> list[Ticket]:
        return [t for t in self.tickets if t.agent_type != AgentType.marketing]

    @property
    def marketing_ticket(self) -> Ticket | None:
        for t in self.tickets:
            if t.agent_type == AgentType.marketing:
                return t
        return None

    @property
    def stale_ticket_count(self) -> int:
        return sum(1 for t in self.tickets if t.is_stale)

    @property
    def open_bug_count(self) -> int:
        return sum(1 for t in self.tickets if t.is_bug and t.status not in (TicketStatus.done, TicketStatus.cancelled))


# ---------------------------------------------------------------------------
# PM Agent conversation messages
# ---------------------------------------------------------------------------


class StoryMessage(Base):
    __tablename__ = "story_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    story: Mapped[Story] = relationship("Story", back_populates="pm_messages", foreign_keys=[story_id])

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role.value, "content": self.content}


# ---------------------------------------------------------------------------
# Growth Agent conversation messages
# ---------------------------------------------------------------------------


class GrowthMessage(Base):
    __tablename__ = "growth_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    story: Mapped[Story] = relationship("Story", back_populates="growth_messages")

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role.value, "content": self.content}


# ---------------------------------------------------------------------------
# Ticket (engineering task inside a story)
# ---------------------------------------------------------------------------


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id", ondelete="CASCADE"), nullable=False)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    acceptance_criteria: Mapped[str | None] = mapped_column(Text, nullable=True)

    # PRD link
    prd_anchor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Classification
    agent_type: Mapped[AgentType] = mapped_column(Enum(AgentType), nullable=False)
    runtime: Mapped[Runtime] = mapped_column(Enum(Runtime), default=Runtime.claude, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    complexity: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)

    # Execution
    status: Mapped[TicketStatus] = mapped_column(
        Enum(TicketStatus), default=TicketStatus.pending, nullable=False
    )
    branch_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pr_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    context_files: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Dependency (stores ticket id this depends on)
    depends_on_index: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Execution index (order within story)
    ticket_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Bug tracking
    is_bug: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    bug_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    story: Mapped[Story] = relationship("Story", back_populates="tickets")
    executions: Mapped[list[Execution]] = relationship(
        "Execution", back_populates="ticket", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Ticket id={self.id} title={self.title!r} status={self.status}>"

    @property
    def is_terminal(self) -> bool:
        return self.status in (TicketStatus.done, TicketStatus.failed, TicketStatus.cancelled)

    @property
    def is_running_too_long(self) -> bool:
        if self.status != TicketStatus.in_progress or not self.started_at:
            return False
        start = self.started_at if self.started_at.tzinfo else self.started_at.replace(tzinfo=UTC)
        elapsed = (datetime.now(UTC) - start).total_seconds()
        return elapsed > 3 * 60 * 60  # 3 hours

    @property
    def active_execution(self) -> Execution | None:
        for ex in self.executions:
            if ex.status == "running":
                return ex
        return None


# ---------------------------------------------------------------------------
# Execution (one agent run per ticket attempt)
# ---------------------------------------------------------------------------


class Execution(Base):
    __tablename__ = "executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False)

    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False)
    runtime: Mapped[Runtime] = mapped_column(Enum(Runtime), nullable=False)

    # Cost tracking
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Output
    workspace_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Timestamps
    started_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    ticket: Mapped[Ticket] = relationship("Ticket", back_populates="executions")
    logs: Mapped[list[ExecutionLog]] = relationship(
        "ExecutionLog", back_populates="execution", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Execution id={self.id} ticket_id={self.ticket_id} status={self.status}>"


# ---------------------------------------------------------------------------
# Execution log (streaming output from agent runs)
# ---------------------------------------------------------------------------


class ExecutionLog(Base):
    __tablename__ = "execution_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    execution_id: Mapped[int] = mapped_column(
        ForeignKey("executions.id", ondelete="CASCADE"), nullable=False
    )
    log_type: Mapped[str] = mapped_column(String(30), nullable=False)  # stdout, stderr, info
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    execution: Mapped[Execution] = relationship("Execution", back_populates="logs")
