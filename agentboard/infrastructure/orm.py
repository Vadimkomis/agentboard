"""SQLAlchemy records for browser-v0 persistence."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class BrowserBase(DeclarativeBase):
    """Declarative base kept separate from the legacy Story/Ticket metadata."""


class ProjectRecord(BrowserBase):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("key", name="uq_projects_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    repository_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class FeatureRecord(BrowserBase):
    __tablename__ = "features"
    __table_args__ = (
        CheckConstraint("number > 0", name="ck_features_number_positive"),
        CheckConstraint("rank > 0", name="ck_features_rank_positive"),
        CheckConstraint(
            "estimate IS NULL OR estimate >= 0",
            name="ck_features_estimate_nonnegative",
        ),
        CheckConstraint(
            "planning_stage IN ('inbox', 'clarifying', 'spec', 'evals', 'design', 'design_review')",
            name="ck_features_planning_stage",
        ),
        CheckConstraint(
            "engineering_state IS NULL OR engineering_state IN "
            "('ready_for_engineering', 'working', 'in_review', "
            "'human_review', 'ready_to_merge', 'done')",
            name="ck_features_engineering_state",
        ),
        UniqueConstraint("project_id", "number", name="uq_features_project_number"),
        UniqueConstraint("project_id", "rank", name="uq_features_project_rank"),
        Index("ix_features_project_id", "project_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    planning_stage: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'inbox'")
    )
    engineering_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    priority: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'medium'")
    )
    estimate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_design_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class SprintRecord(BrowserBase):
    __tablename__ = "sprints"
    __table_args__ = (
        CheckConstraint("number > 0", name="ck_sprints_number_positive"),
        CheckConstraint(
            "state IN ('planned', 'active', 'completed')",
            name="ck_sprints_state",
        ),
        UniqueConstraint("project_id", "number", name="uq_sprints_project_number"),
        Index("ix_sprints_project_id", "project_id"),
        Index(
            "uq_sprints_one_active_per_project",
            "project_id",
            unique=True,
            sqlite_where=text("state = 'active'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'planned'"))
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class SprintFeatureRecord(BrowserBase):
    __tablename__ = "sprint_features"
    __table_args__ = (
        CheckConstraint("sprint_rank > 0", name="ck_sprint_features_rank_positive"),
        UniqueConstraint("sprint_id", "sprint_rank", name="uq_sprint_features_sprint_rank"),
        Index("ix_sprint_features_feature_id", "feature_id"),
    )

    sprint_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sprints.id", ondelete="CASCADE"),
        primary_key=True,
    )
    feature_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("features.id", ondelete="CASCADE"),
        primary_key=True,
    )
    sprint_rank: Mapped[int] = mapped_column(Integer, nullable=False)


class AuditEventRecord(BrowserBase):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_project_created_at", "project_id", "created_at"),
        Index("ix_audit_events_feature_id", "feature_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    feature_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("features.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column("type", String(100), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
