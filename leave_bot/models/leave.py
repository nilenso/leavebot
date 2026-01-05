"""Leave record model with enums."""

from datetime import date, datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship

from leave_bot.database import Base

if TYPE_CHECKING:
    from leave_bot.models.user import User


class LeaveType(str, Enum):
    """Type of leave - full day or half day."""

    FULL = "full"
    HALF_AM = "half_am"  # Morning half (11:00-15:00)
    HALF_PM = "half_pm"  # Afternoon half (15:00-19:00)


class LeaveCategory(str, Enum):
    """Category of leave for Harvest task selection."""

    VACATION = "vacation"
    SICK = "sick"


class LeaveStatus(str, Enum):
    """Status of leave record processing."""

    PENDING = "pending"  # Awaiting user confirmation
    CONFIRMED = "confirmed"  # User confirmed, awaiting sync
    COMPLETED = "completed"  # Successfully synced
    FAILED = "failed"  # Sync failed, needs retry
    CANCELLED = "cancelled"  # User cancelled or deleted


class LeaveRecord(Base):
    """Record of a leave day."""

    __tablename__ = "leave_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # User reference
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Leave details
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    leave_type: Mapped[LeaveType] = mapped_column(
        ENUM(LeaveType, name="leave_type", create_type=False),
        nullable=False,
        default=LeaveType.FULL,
    )
    leave_category: Mapped[LeaveCategory] = mapped_column(
        ENUM(LeaveCategory, name="leave_category", create_type=False),
        nullable=False,
        default=LeaveCategory.VACATION,
    )

    # Slack context
    slack_message_ts: Mapped[str | None] = mapped_column(String(30), nullable=True)
    slack_channel_id: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # External sync IDs
    calendar_event_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    harvest_entry_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Status tracking
    status: Mapped[LeaveStatus] = mapped_column(
        ENUM(LeaveStatus, name="leave_status", create_type=False),
        nullable=False,
        default=LeaveStatus.PENDING,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="leave_records")

    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_user_date"),)

    def __repr__(self) -> str:
        return f"<LeaveRecord {self.date} {self.leave_type.value} ({self.status.value})>"
