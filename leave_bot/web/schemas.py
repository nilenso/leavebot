"""Pydantic schemas for API requests and responses."""

from datetime import date, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

from leave_bot.models.leave import LeaveCategory, LeaveStatus, LeaveType

T = TypeVar("T")


# Pagination
class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response wrapper."""

    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int


# User schemas
class UserBase(BaseModel):
    """Base user schema."""

    slack_user_id: str = Field(..., max_length=20)
    slack_display_name: str = Field(..., max_length=100)
    email: str | None = Field(None, max_length=255)
    slack_timezone: str = Field(default="Asia/Kolkata", max_length=50)
    harvest_user_id: int | None = None
    is_active: bool = True


class UserCreate(UserBase):
    """Schema for creating a user."""

    pass


class UserUpdate(BaseModel):
    """Schema for updating a user."""

    slack_display_name: str | None = Field(None, max_length=100)
    email: str | None = Field(None, max_length=255)
    slack_timezone: str | None = Field(None, max_length=50)
    harvest_user_id: int | None = None
    is_active: bool | None = None


class UserResponse(UserBase):
    """Schema for user response."""

    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Leave schemas
class LeaveRecordResponse(BaseModel):
    """Schema for leave record response."""

    id: int
    user_id: int
    date: date
    leave_type: LeaveType
    leave_category: LeaveCategory
    slack_message_ts: str | None
    slack_channel_id: str | None
    calendar_event_id: str | None
    harvest_entry_id: int | None
    status: LeaveStatus
    error_message: str | None
    retry_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LeaveRecordWithUser(LeaveRecordResponse):
    """Leave record with user details."""

    user: UserResponse


# Configuration schemas
class ConfigurationResponse(BaseModel):
    """Schema for configuration response."""

    key: str
    value: dict[str, Any]
    updated_at: datetime

    class Config:
        from_attributes = True


class ConfigurationUpdate(BaseModel):
    """Schema for updating configuration."""

    value: dict[str, Any]


# Health check schemas
class ServiceHealth(BaseModel):
    """Health status of a single service."""

    status: str  # "healthy", "unhealthy", "unknown"
    message: str | None = None


class HealthResponse(BaseModel):
    """Overall health response."""

    status: str
    database: ServiceHealth
    slack: ServiceHealth
    calendar: ServiceHealth
    harvest: ServiceHealth


# Import schemas
class ImportResult(BaseModel):
    """Result of user import."""

    imported: int
    updated: int
    skipped: int
    errors: list[str]
