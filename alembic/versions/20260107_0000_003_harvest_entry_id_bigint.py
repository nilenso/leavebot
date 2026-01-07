"""Change harvest_entry_id to BIGINT

Revision ID: 003
Revises: 002
Create Date: 2026-01-07

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE leave_records ALTER COLUMN harvest_entry_id TYPE BIGINT")


def downgrade() -> None:
    op.execute("ALTER TABLE leave_records ALTER COLUMN harvest_entry_id TYPE INTEGER")
