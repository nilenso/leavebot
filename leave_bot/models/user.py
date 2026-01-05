"""User model for Slack-Harvest user mapping."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from leave_bot.database import Base

if TYPE_CHECKING:
    from leave_bot.models.leave import LeaveRecord
    from leave_bot.models.pending_action import PendingAction


class User(Base):
    """User mapping between Slack and Harvest."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Slack identifiers
    slack_user_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    slack_display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    slack_timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="Asia/Kolkata")

    # Harvest identifiers
    harvest_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

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
    leave_records: Mapped[list["LeaveRecord"]] = relationship(
        "LeaveRecord", back_populates="user", lazy="selectin"
    )
    pending_actions: Mapped[list["PendingAction"]] = relationship(
        "PendingAction", back_populates="user", lazy="selectin"
    )

    __table_args__ = (Index("ix_users_harvest_user_id", harvest_user_id),)

    def __repr__(self) -> str:
        return f"<User {self.slack_display_name} ({self.slack_user_id})>"
