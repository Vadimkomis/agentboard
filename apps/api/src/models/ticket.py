import uuid
from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    column_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("board_columns.id", ondelete="CASCADE")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE")
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )

    # Core fields
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0)

    # Status
    status: Mapped[str] = mapped_column(String(50), default="backlog", index=True)
    # backlog, triaging, ready, in_progress, in_review, done, failed, cancelled

    # PM Agent classification
    agent_type: Mapped[str | None] = mapped_column(String(50))
    # pm, mobile, backend, frontend, devops, qa, fullstack, docs
    runtime: Mapped[str | None] = mapped_column(String(50))  # claude, codex
    priority: Mapped[str | None] = mapped_column(String(20))  # low, medium, high, critical
    complexity: Mapped[str | None] = mapped_column(String(20))  # trivial, simple, medium, complex
    refined_description: Mapped[str | None] = mapped_column(Text)
    acceptance_criteria: Mapped[str | None] = mapped_column(Text)
    context_files: Mapped[dict | None] = mapped_column(JSONB)  # list of relevant file paths
    triage_reasoning: Mapped[str | None] = mapped_column(Text)

    # Git integration
    branch_name: Mapped[str | None] = mapped_column(String(255))
    pr_url: Mapped[str | None] = mapped_column(Text)
    pr_number: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    column: Mapped["BoardColumn"] = relationship(back_populates="tickets")  # noqa: F821
    executions: Mapped[list["Execution"]] = relationship(back_populates="ticket")  # noqa: F821
