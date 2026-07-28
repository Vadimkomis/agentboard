"""Add browser-v0 project, feature, sprint, and audit persistence.

Revision ID: 0001_browser_domain
Revises:
Create Date: 2026-07-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_browser_domain"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _create_projects()
    _create_features()
    _create_sprints()
    _create_sprint_features()
    _create_audit_events()
    _create_integrity_triggers()


def downgrade() -> None:
    _drop_integrity_triggers()
    op.drop_table("audit_events")
    op.drop_table("sprint_features")
    op.drop_index("uq_sprints_one_active_per_project", table_name="sprints")
    op.drop_table("sprints")
    op.drop_table("features")
    op.drop_table("projects")


def _create_projects() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("repository_url", sa.String(length=2048), nullable=False),
        sa.Column("default_branch", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
        sa.UniqueConstraint("key", name="uq_projects_key"),
    )


def _create_features() -> None:
    op.create_table(
        "features",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column(
            "planning_stage",
            sa.String(length=32),
            server_default=sa.text("'inbox'"),
            nullable=False,
        ),
        sa.Column("engineering_state", sa.String(length=32), nullable=True),
        sa.Column(
            "priority",
            sa.String(length=16),
            server_default=sa.text("'medium'"),
            nullable=False,
        ),
        sa.Column("estimate", sa.Integer(), nullable=True),
        sa.Column("owner", sa.String(length=255), nullable=True),
        sa.Column("approved_design_hash", sa.String(length=128), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "engineering_state IS NULL OR engineering_state IN "
            "('ready_for_engineering', 'working', 'in_review', "
            "'human_review', 'ready_to_merge', 'done')",
            name="ck_features_engineering_state",
        ),
        sa.CheckConstraint(
            "estimate IS NULL OR estimate >= 0",
            name="ck_features_estimate_nonnegative",
        ),
        sa.CheckConstraint("number > 0", name="ck_features_number_positive"),
        sa.CheckConstraint(
            "planning_stage IN ('inbox', 'clarifying', 'spec', 'evals', 'design', 'design_review')",
            name="ck_features_planning_stage",
        ),
        sa.CheckConstraint("rank > 0", name="ck_features_rank_positive"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_features_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_features")),
        sa.UniqueConstraint("project_id", "number", name="uq_features_project_number"),
        sa.UniqueConstraint("project_id", "rank", name="uq_features_project_rank"),
    )
    op.create_index("ix_features_project_id", "features", ["project_id"], unique=False)


def _create_sprints() -> None:
    op.create_table(
        "sprints",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("goal", sa.Text(), nullable=True),
        sa.Column(
            "state",
            sa.String(length=16),
            server_default=sa.text("'planned'"),
            nullable=False,
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("number > 0", name="ck_sprints_number_positive"),
        sa.CheckConstraint(
            "state IN ('planned', 'active', 'completed')",
            name="ck_sprints_state",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_sprints_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sprints")),
        sa.UniqueConstraint("project_id", "number", name="uq_sprints_project_number"),
    )
    op.create_index("ix_sprints_project_id", "sprints", ["project_id"], unique=False)
    op.create_index(
        "uq_sprints_one_active_per_project",
        "sprints",
        ["project_id"],
        unique=True,
        sqlite_where=sa.text("state = 'active'"),
    )


def _create_sprint_features() -> None:
    op.create_table(
        "sprint_features",
        sa.Column("sprint_id", sa.Integer(), nullable=False),
        sa.Column("feature_id", sa.Integer(), nullable=False),
        sa.Column("sprint_rank", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "sprint_rank > 0",
            name="ck_sprint_features_rank_positive",
        ),
        sa.ForeignKeyConstraint(
            ["feature_id"],
            ["features.id"],
            name=op.f("fk_sprint_features_feature_id_features"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sprint_id"],
            ["sprints.id"],
            name=op.f("fk_sprint_features_sprint_id_sprints"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "sprint_id",
            "feature_id",
            name=op.f("pk_sprint_features"),
        ),
        sa.UniqueConstraint(
            "sprint_id",
            "sprint_rank",
            name="uq_sprint_features_sprint_rank",
        ),
    )
    op.create_index(
        "ix_sprint_features_feature_id",
        "sprint_features",
        ["feature_id"],
        unique=False,
    )


def _create_audit_events() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("feature_id", sa.Integer(), nullable=True),
        sa.Column("type", sa.String(length=100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["feature_id"],
            ["features.id"],
            name=op.f("fk_audit_events_feature_id_features"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_audit_events_project_id_projects"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(
        "ix_audit_events_feature_id",
        "audit_events",
        ["feature_id"],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_project_created_at",
        "audit_events",
        ["project_id", "created_at"],
        unique=False,
    )


def _create_integrity_triggers() -> None:
    op.execute(_SPRINT_FEATURE_INSERT_TRIGGER)
    op.execute(_SPRINT_FEATURE_UPDATE_TRIGGER)
    op.execute(_FEATURE_PROJECT_UPDATE_TRIGGER)
    op.execute(_SPRINT_PROJECT_UPDATE_TRIGGER)
    op.execute(_AUDIT_EVENT_INSERT_TRIGGER)
    op.execute(_AUDIT_EVENT_UPDATE_TRIGGER)
    op.execute(_FEATURE_PROJECT_AUDIT_UPDATE_TRIGGER)


def _drop_integrity_triggers() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_feature_project_audit_update")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_events_project_update")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_events_project_insert")
    op.execute("DROP TRIGGER IF EXISTS trg_sprint_project_membership_update")
    op.execute("DROP TRIGGER IF EXISTS trg_feature_project_membership_update")
    op.execute("DROP TRIGGER IF EXISTS trg_sprint_features_project_update")
    op.execute("DROP TRIGGER IF EXISTS trg_sprint_features_project_insert")


_SPRINT_FEATURE_INSERT_TRIGGER = """
CREATE TRIGGER trg_sprint_features_project_insert
BEFORE INSERT ON sprint_features
FOR EACH ROW
WHEN EXISTS (
    SELECT 1
    FROM sprints AS sprint
    JOIN features AS feature
      ON sprint.project_id <> feature.project_id
    WHERE sprint.id = NEW.sprint_id
      AND feature.id = NEW.feature_id
)
BEGIN
    SELECT RAISE(ABORT, 'sprint membership cannot cross project boundaries');
END
"""

_SPRINT_FEATURE_UPDATE_TRIGGER = """
CREATE TRIGGER trg_sprint_features_project_update
BEFORE UPDATE OF sprint_id, feature_id ON sprint_features
FOR EACH ROW
WHEN EXISTS (
    SELECT 1
    FROM sprints AS sprint
    JOIN features AS feature
      ON sprint.project_id <> feature.project_id
    WHERE sprint.id = NEW.sprint_id
      AND feature.id = NEW.feature_id
)
BEGIN
    SELECT RAISE(ABORT, 'sprint membership cannot cross project boundaries');
END
"""

_FEATURE_PROJECT_UPDATE_TRIGGER = """
CREATE TRIGGER trg_feature_project_membership_update
BEFORE UPDATE OF project_id ON features
FOR EACH ROW
WHEN EXISTS (
    SELECT 1
    FROM sprint_features AS membership
    JOIN sprints AS sprint
      ON sprint.id = membership.sprint_id
    WHERE membership.feature_id = OLD.id
      AND sprint.project_id <> NEW.project_id
)
BEGIN
    SELECT RAISE(ABORT, 'feature project cannot invalidate sprint membership');
END
"""

_SPRINT_PROJECT_UPDATE_TRIGGER = """
CREATE TRIGGER trg_sprint_project_membership_update
BEFORE UPDATE OF project_id ON sprints
FOR EACH ROW
WHEN EXISTS (
    SELECT 1
    FROM sprint_features AS membership
    JOIN features AS feature
      ON feature.id = membership.feature_id
    WHERE membership.sprint_id = OLD.id
      AND feature.project_id <> NEW.project_id
)
BEGIN
    SELECT RAISE(ABORT, 'sprint project cannot invalidate feature membership');
END
"""

_AUDIT_EVENT_INSERT_TRIGGER = """
CREATE TRIGGER trg_audit_events_project_insert
BEFORE INSERT ON audit_events
FOR EACH ROW
WHEN NEW.feature_id IS NOT NULL
 AND EXISTS (
    SELECT 1
    FROM features AS feature
    WHERE feature.id = NEW.feature_id
      AND feature.project_id <> NEW.project_id
)
BEGIN
    SELECT RAISE(ABORT, 'audit Feature cannot cross project boundaries');
END
"""

_AUDIT_EVENT_UPDATE_TRIGGER = """
CREATE TRIGGER trg_audit_events_project_update
BEFORE UPDATE OF project_id, feature_id ON audit_events
FOR EACH ROW
WHEN NEW.feature_id IS NOT NULL
 AND EXISTS (
    SELECT 1
    FROM features AS feature
    WHERE feature.id = NEW.feature_id
      AND feature.project_id <> NEW.project_id
)
BEGIN
    SELECT RAISE(ABORT, 'audit Feature cannot cross project boundaries');
END
"""

_FEATURE_PROJECT_AUDIT_UPDATE_TRIGGER = """
CREATE TRIGGER trg_feature_project_audit_update
BEFORE UPDATE OF project_id ON features
FOR EACH ROW
WHEN EXISTS (
    SELECT 1
    FROM audit_events AS event
    WHERE event.feature_id = OLD.id
      AND event.project_id <> NEW.project_id
)
BEGIN
    SELECT RAISE(ABORT, 'Feature project cannot invalidate audit history');
END
"""
