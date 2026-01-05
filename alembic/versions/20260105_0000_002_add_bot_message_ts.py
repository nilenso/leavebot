"""Add slack_bot_message_ts to pending_actions.

Revision ID: 002
Revises: 001
Create Date: 2026-01-05
"""

from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pending_actions",
        sa.Column("slack_bot_message_ts", sa.String(30), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pending_actions", "slack_bot_message_ts")
