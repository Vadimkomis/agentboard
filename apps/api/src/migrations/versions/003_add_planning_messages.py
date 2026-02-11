"""add planning_messages table

Revision ID: 003
Revises: 002
Create Date: 2025-01-01 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "planning_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "ticket_id",
            sa.Uuid(),
            sa.ForeignKey("tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "is_streaming", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_planning_messages_ticket_id",
        "planning_messages",
        ["ticket_id"],
    )
    op.create_unique_constraint(
        "uq_ticket_sequence",
        "planning_messages",
        ["ticket_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_ticket_sequence", "planning_messages", type_="unique")
    op.drop_index("ix_planning_messages_ticket_id", table_name="planning_messages")
    op.drop_table("planning_messages")
