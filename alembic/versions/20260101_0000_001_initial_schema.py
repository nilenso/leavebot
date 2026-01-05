"""Initial schema with all tables

Revision ID: 001
Revises:
Create Date: 2026-01-01 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum types
    op.execute("CREATE TYPE leave_type AS ENUM ('full', 'half_am', 'half_pm')")
    op.execute("CREATE TYPE leave_category AS ENUM ('vacation', 'sick')")
    op.execute(
        "CREATE TYPE leave_status AS ENUM ('pending', 'confirmed', 'completed', 'failed', 'cancelled')"
    )
    op.execute("CREATE TYPE action_type AS ENUM ('create_leave', 'cancel_leave')")
    op.execute(
        "CREATE TYPE action_status AS ENUM ('pending', 'confirmed', 'processing', 'completed', 'expired', 'cancelled')"
    )

    # Create users table
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slack_user_id", sa.String(20), nullable=False),
        sa.Column("slack_display_name", sa.String(100), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("slack_timezone", sa.String(50), nullable=False, server_default="Asia/Kolkata"),
        sa.Column("harvest_user_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slack_user_id"),
    )
    op.create_index("ix_users_slack_user_id", "users", ["slack_user_id"])
    op.create_index("ix_users_harvest_user_id", "users", ["harvest_user_id"])

    # Create leave_records table
    op.create_table(
        "leave_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column(
            "leave_type",
            postgresql.ENUM("full", "half_am", "half_pm", name="leave_type", create_type=False),
            nullable=False,
            server_default="full",
        ),
        sa.Column(
            "leave_category",
            postgresql.ENUM("vacation", "sick", name="leave_category", create_type=False),
            nullable=False,
            server_default="vacation",
        ),
        sa.Column("slack_message_ts", sa.String(30), nullable=True),
        sa.Column("slack_channel_id", sa.String(20), nullable=True),
        sa.Column("calendar_event_id", sa.String(100), nullable=True),
        sa.Column("harvest_entry_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending",
                "confirmed",
                "completed",
                "failed",
                "cancelled",
                name="leave_status",
                create_type=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "date", name="uq_user_date"),
    )
    op.create_index("ix_leave_records_user_id", "leave_records", ["user_id"])
    op.create_index("ix_leave_records_date", "leave_records", ["date"])
    op.create_index("ix_leave_records_status", "leave_records", ["status"])

    # Create pending_actions table
    op.create_table(
        "pending_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "action_type",
            postgresql.ENUM("create_leave", "cancel_leave", name="action_type", create_type=False),
            nullable=False,
        ),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("slack_event_id", sa.String(50), nullable=True),
        sa.Column("slack_message_ts", sa.String(30), nullable=True),
        sa.Column("slack_channel_id", sa.String(20), nullable=True),
        sa.Column("slack_thread_ts", sa.String(30), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending",
                "confirmed",
                "processing",
                "completed",
                "expired",
                "cancelled",
                name="action_status",
                create_type=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pending_actions_user_id", "pending_actions", ["user_id"])
    op.create_index("ix_pending_actions_status", "pending_actions", ["status"])
    op.create_index(
        "ix_pending_actions_slack_event_id",
        "pending_actions",
        ["slack_event_id"],
        unique=True,
        postgresql_where=sa.text("slack_event_id IS NOT NULL"),
    )
    op.create_index(
        "ix_pending_actions_status_expires", "pending_actions", ["status", "expires_at"]
    )

    # Create configurations table
    op.create_table(
        "configurations",
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("key"),
    )

    # Insert default configurations
    op.execute("""
        INSERT INTO configurations (key, value) VALUES
        ('trigger_keywords', '["leave", "ooo", "wfh", "sick", "vacation", "pto", "day off"]'),
        ('half_day_times', '{"am_start": "11:00", "am_end": "15:00", "pm_start": "15:00", "pm_end": "19:00"}'),
        ('default_timezone', '"Asia/Kolkata"'),
        ('pending_action_expiry_minutes', '60')
    """)


def downgrade() -> None:
    op.drop_table("configurations")
    op.drop_table("pending_actions")
    op.drop_table("leave_records")
    op.drop_table("users")

    op.execute("DROP TYPE action_status")
    op.execute("DROP TYPE action_type")
    op.execute("DROP TYPE leave_status")
    op.execute("DROP TYPE leave_category")
    op.execute("DROP TYPE leave_type")
