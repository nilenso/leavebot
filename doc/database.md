# Database

Database schema, models, relationships, and migrations.

## Overview

The Leave Bot uses PostgreSQL 16 with SQLAlchemy 2.0 (async) for data persistence. Migrations are managed with Alembic.

## Entity Relationship Diagram

```
┌─────────────────────┐       ┌─────────────────────┐
│       users         │       │    leave_records    │
├─────────────────────┤       ├─────────────────────┤
│ id (PK)             │───┐   │ id (PK)             │
│ slack_user_id (UK)  │   │   │ user_id (FK)        │──┐
│ slack_display_name  │   │   │ date                │  │
│ email               │   │   │ leave_type          │  │
│ harvest_user_id     │   │   │ leave_category      │  │
│ slack_timezone      │   │   │ slack_message_ts    │  │
│ is_active           │   │   │ slack_channel_id    │  │
│ created_at          │   │   │ calendar_event_id   │  │
│ updated_at          │   │   │ harvest_entry_id    │  │
└─────────────────────┘   │   │ status              │  │
                          │   │ error_message       │  │
                          │   │ retry_count         │  │
                          │   │ created_at          │  │
                          │   │ updated_at          │  │
                          │   └─────────────────────┘  │
                          │                            │
                          │   ┌─────────────────────┐  │
                          │   │  pending_actions    │  │
                          │   ├─────────────────────┤  │
                          └──▶│ id (PK, UUID)       │  │
                              │ user_id (FK)        │◀─┘
                              │ action_type         │
                              │ payload (JSONB)     │
                              │ slack_event_id      │
                              │ slack_message_ts    │
                              │ slack_channel_id    │
                              │ slack_thread_ts     │
                              │ slack_bot_message_ts│
                              │ expires_at          │
                              │ status              │
                              │ created_at          │
                              └─────────────────────┘

┌─────────────────────┐
│   configuration     │
├─────────────────────┤
│ key (PK)            │
│ value (JSONB)       │
│ updated_at          │
└─────────────────────┘
```

## Models

### User Model

Location: `leave_bot/models/user.py`

Maps Slack users to Harvest accounts and stores timezone information.

```python
class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int]                           # Primary key
    slack_user_id: Mapped[str]                # Unique, e.g., "U01ABC123"
    slack_display_name: Mapped[str]           # Display name from Slack
    email: Mapped[str | None]                 # For matching across systems
    harvest_user_id: Mapped[int | None]       # Harvest user ID
    slack_timezone: Mapped[str | None]        # e.g., "Asia/Kolkata"
    is_active: Mapped[bool] = True            # Soft delete flag
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
```

**Indexes:**
- `idx_users_slack_id` on `slack_user_id` (unique)
- `idx_users_harvest_id` on `harvest_user_id`

### LeaveRecord Model

Location: `leave_bot/models/leave.py`

Individual leave day entries with sync status.

```python
class LeaveType(str, Enum):
    full = "full"          # Full day leave
    half_am = "half_am"    # Morning half: 11:00-15:00
    half_pm = "half_pm"    # Afternoon half: 15:00-19:00

class LeaveCategory(str, Enum):
    vacation = "vacation"  # Maps to Harvest vacation task
    sick = "sick"          # Maps to Harvest sick leave task

class LeaveStatus(str, Enum):
    pending = "pending"        # Awaiting user confirmation
    confirmed = "confirmed"    # User confirmed, awaiting sync
    completed = "completed"    # Calendar + Harvest synced
    failed = "failed"          # Sync failed (retryable)
    cancelled = "cancelled"    # User cancelled

class LeaveRecord(Base):
    __tablename__ = "leave_records"
    
    id: Mapped[int]                           # Primary key
    user_id: Mapped[int]                      # FK to users
    date: Mapped[date]                        # Leave date
    leave_type: Mapped[LeaveType]             # full/half_am/half_pm
    leave_category: Mapped[LeaveCategory]     # vacation/sick
    slack_message_ts: Mapped[str | None]      # Original message timestamp
    slack_channel_id: Mapped[str | None]      # Channel ID
    calendar_event_id: Mapped[str | None]     # Google Calendar event ID
    harvest_entry_id: Mapped[int | None]      # Harvest time entry ID
    status: Mapped[LeaveStatus]               # Current status
    error_message: Mapped[str | None]         # Error details if failed
    retry_count: Mapped[int] = 0              # Number of retry attempts
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    
    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_user_date"),
    )
```

**Indexes:**
- `idx_leave_records_user_date` on `(user_id, date)`
- `idx_leave_records_status` on `status`

**Constraints:**
- Unique constraint on `(user_id, date)` - one record per user per day

### PendingAction Model

Location: `leave_bot/models/pending_action.py`

Temporary storage for the confirmation flow.

```python
class ActionType(str, Enum):
    create_leave = "create_leave"
    cancel_leave = "cancel_leave"

class ActionStatus(str, Enum):
    pending = "pending"        # Awaiting user action
    confirmed = "confirmed"    # User confirmed, awaiting worker
    processing = "processing"  # Worker is processing
    completed = "completed"    # Successfully processed
    expired = "expired"        # Timed out
    cancelled = "cancelled"    # User cancelled

class PendingAction(Base):
    __tablename__ = "pending_actions"
    
    id: Mapped[uuid.UUID]                     # UUID primary key
    user_id: Mapped[int]                      # FK to users
    action_type: Mapped[ActionType]           # create_leave/cancel_leave
    payload: Mapped[dict[str, Any]]           # JSONB with parsed dates
    slack_event_id: Mapped[str | None]        # For deduplication
    slack_message_ts: Mapped[str | None]      # User's message
    slack_channel_id: Mapped[str | None]      # Channel
    slack_thread_ts: Mapped[str | None]       # Thread parent
    slack_bot_message_ts: Mapped[str | None]  # Bot's reply (for updates)
    status: Mapped[ActionStatus]              # Current status
    expires_at: Mapped[datetime]              # Auto-expire time
    created_at: Mapped[datetime]
```

**Indexes:**
- `idx_pending_actions_status` on `(status, expires_at)`
- `idx_pending_actions_event_id` on `slack_event_id` (unique, partial)

### Configuration Model

Location: `leave_bot/models/configuration.py`

Key-value storage for runtime settings.

```python
class Configuration(Base):
    __tablename__ = "configuration"
    
    key: Mapped[str]                          # Primary key
    value: Mapped[dict[str, Any]]             # JSONB value
    updated_at: Mapped[datetime]
```

## Payload Structure

The `pending_actions.payload` JSONB column stores parsed leave data:

```json
{
    "dates": [
        {
            "date": "2026-01-06",
            "type": "full",
            "category": "vacation"
        },
        {
            "date": "2026-01-07",
            "type": "half_am",
            "category": "vacation"
        }
    ],
    "original_text_summary": "Leave on 6th and half day on 7th",
    "ambiguity_notes": null
}
```

## Status Transitions

### PendingAction Status Flow

```
                  ┌─────────┐
                  │ pending │
                  └────┬────┘
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
   ┌───────────┐ ┌───────────┐ ┌─────────┐
   │ confirmed │ │ cancelled │ │ expired │
   └─────┬─────┘ └───────────┘ └─────────┘
         │
         ▼
   ┌────────────┐
   │ processing │
   └─────┬──────┘
         │
         ▼
   ┌───────────┐
   │ completed │
   └───────────┘
```

### LeaveRecord Status Flow

```
         ┌─────────┐
         │ pending │
         └────┬────┘
              │
    ┌─────────┼─────────┐
    ▼         ▼         ▼
┌───────┐ ┌─────────┐ ┌───────────┐
│confirmed│ │cancelled│ │           │
└────┬────┘ └─────────┘ │           │
     │                  │           │
     ▼                  │           │
┌───────────┐           │           │
│ completed │           │           │
└───────────┘           │           │
     ▲                  │           │
     │                  ▼           │
     │              ┌────────┐      │
     └──────────────│ failed │──────┘
        (retry)     └────────┘
```

## Database Connection

Location: `leave_bot/database.py`

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

# Async engine setup
engine = create_async_engine(
    settings.database_url.replace("postgresql://", "postgresql+asyncpg://"),
    echo=settings.debug,
)

# Session factory
async_session = async_sessionmaker(engine, expire_on_commit=False)
```

## Migrations

Migrations are managed with Alembic.

### Running Migrations

```bash
# Apply all migrations
uv run leave-bot migrate

# Or using Alembic directly
uv run alembic upgrade head
```

### Creating New Migrations

```bash
# Auto-generate from model changes
uv run alembic revision --autogenerate -m "description"

# Create empty migration
uv run alembic revision -m "description"
```

### Migration Files

Located in `alembic/versions/`

## Queries

### Common Query Patterns

**Get user by Slack ID:**
```python
async def get_user_by_slack_id(session, slack_user_id: str) -> User | None:
    result = await session.execute(
        select(User).where(User.slack_user_id == slack_user_id)
    )
    return result.scalar_one_or_none()
```

**Get pending leaves for user:**
```python
async def get_pending_leaves(session, user_id: int) -> list[LeaveRecord]:
    result = await session.execute(
        select(LeaveRecord)
        .where(LeaveRecord.user_id == user_id)
        .where(LeaveRecord.status.in_([LeaveStatus.pending, LeaveStatus.confirmed]))
    )
    return result.scalars().all()
```

**Check for date conflicts (in-flight leaves only):**
```python
async def check_existing_leaves(session, user_id: int, dates: list[date]) -> list[date]:
    # Only pending/confirmed are conflicts—completed leaves may have been deleted externally
    result = await session.execute(
        select(LeaveRecord.date)
        .where(LeaveRecord.user_id == user_id)
        .where(LeaveRecord.date.in_(dates))
        .where(LeaveRecord.status.in_([LeaveStatus.pending, LeaveStatus.confirmed]))
    )
    return list(result.scalars().all())
```

## Backup & Restore

### Backup

```bash
# Using docker-compose
docker compose exec db pg_dump -U leavebot leavebot > backup.sql

# Direct connection
pg_dump -h localhost -U leavebot leavebot > backup.sql
```

### Restore

```bash
# Using docker-compose
docker compose exec -T db psql -U leavebot leavebot < backup.sql

# Direct connection
psql -h localhost -U leavebot leavebot < backup.sql
```

## Related Documentation

- [Architecture](architecture.md) - System overview
- [Configuration](configuration.md) - DATABASE_URL setup
- [Deployment](deployment.md) - Database in Docker
