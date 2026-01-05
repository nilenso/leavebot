"""Leave record model with enums."""

from datetime import date, datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
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

    full = "full"
    half_am = "half_am"
    half_pm = "half_pm"


class LeaveCategory(str, Enum):
    """Category of leave for Harvest task selection."""

    vacation = "vacation"
    sick = "sick"


class LeaveStatus(str, Enum):
    """Status of leave record processing."""

    pending = "pending"
    confirmed = "confirmed"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


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
        default=LeaveType.full,
    )
    leave_category: Mapped[LeaveCategory] = mapped_column(
        ENUM(LeaveCategory, name="leave_category", create_type=False),
        nullable=False,
        default=LeaveCategory.vacation,
    )

    # Slack context
    slack_message_ts: Mapped[str | None] = mapped_column(String(30), nullable=True)
    slack_channel_id: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # External sync IDs
    calendar_event_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    harvest_entry_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Status tracking
    status: Mapped[LeaveStatus] = mapped_column(
        ENUM(LeaveStatus, name="leave_status", create_type=False),
        nullable=False,
        default=LeaveStatus.pending,
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
