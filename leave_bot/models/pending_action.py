"""Pending action model for tracking user confirmations."""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from leave_bot.database import Base

if TYPE_CHECKING:
    from leave_bot.models.user import User


class ActionType(str, Enum):
    """Type of pending action."""

    CREATE_LEAVE = "create_leave"
    CANCEL_LEAVE = "cancel_leave"


class ActionStatus(str, Enum):
    """Status of pending action."""

    PENDING = "pending"  # Awaiting user confirmation
    CONFIRMED = "confirmed"  # User confirmed, ready for processing
    PROCESSING = "processing"  # Currently being processed
    COMPLETED = "completed"  # Successfully processed
    EXPIRED = "expired"  # Expired without user action
    CANCELLED = "cancelled"  # User cancelled


class PendingAction(Base):
    """Pending action awaiting user confirmation."""

    __tablename__ = "pending_actions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # User reference
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Action details
    action_type: Mapped[ActionType] = mapped_column(
        ENUM(ActionType, name="action_type", create_type=False),
        nullable=False,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    # Slack context for deduplication and response
    slack_event_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    slack_message_ts: Mapped[str | None] = mapped_column(String(30), nullable=True)
    slack_channel_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    slack_thread_ts: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Status tracking
    status: Mapped[ActionStatus] = mapped_column(
        ENUM(ActionStatus, name="action_status", create_type=False),
        nullable=False,
        default=ActionStatus.PENDING,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="pending_actions")

    __table_args__ = (
        Index(
            "ix_pending_actions_slack_event_id",
            slack_event_id,
            unique=True,
            postgresql_where=slack_event_id.isnot(None),
        ),
        Index("ix_pending_actions_status_expires", status, expires_at),
    )

    def __repr__(self) -> str:
        return f"<PendingAction {self.id} {self.action_type.value} ({self.status.value})>"
