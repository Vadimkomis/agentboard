"""Add optimistic backlog versions and durable command receipts.

Revision ID: 0002_browser_ui_security
Revises: 0001_browser_domain
Create Date: 2026-07-27
"""

from __future__ import annotations

import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_browser_ui_security"
down_revision: str | Sequence[str] | None = "0001_browser_domain"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
_PROJECT_KEY_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


def upgrade() -> None:
    _require_url_safe_project_keys()
    op.add_column(
        "projects",
        sa.Column(
            "version",
            sa.Integer(),
            sa.CheckConstraint(
                "version > 0",
                name="ck_projects_version_positive",
            ),
            server_default=sa.text("1"),
            nullable=False,
        ),
    )
    op.create_table(
        "command_receipts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("command_type", sa.String(length=100), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_command_receipts_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_command_receipts")),
        sa.UniqueConstraint(
            "project_id",
            "idempotency_key",
            name="uq_command_receipts_project_key",
        ),
    )
    op.create_index(
        "ix_command_receipts_project_created_at",
        "command_receipts",
        ["project_id", "created_at"],
        unique=False,
    )


def _require_url_safe_project_keys() -> None:
    if op.get_context().as_sql:
        return
    rows = op.get_bind().execute(sa.text('SELECT id, "key" FROM projects ORDER BY id')).mappings()
    invalid = [
        (int(row["id"]), str(row["key"]))
        for row in rows
        if not _is_url_safe_project_key(str(row["key"]))
    ]
    if invalid:
        details = ", ".join(
            f"Project {project_id} has URL-unsafe key {key!r}" for project_id, key in invalid
        )
        raise RuntimeError(
            f"{details}. Before upgrading, update projects.key to 1-64 characters "
            "using only letters, numbers, hyphens, and underscores."
        )


def _is_url_safe_project_key(key: str) -> bool:
    return len(key) <= 64 and _PROJECT_KEY_PATTERN.fullmatch(key) is not None


def downgrade() -> None:
    op.drop_table("command_receipts")
    op.drop_column("projects", "version")
