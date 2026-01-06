# Web Admin

API endpoints and web interface documentation.

## Overview

The Leave Bot includes a FastAPI-based admin interface for managing users, viewing leave records, and configuring the system.

### Access

- **Local**: `http://localhost:8000`
- **Production**: `https://leavebot.nilenso.com` (via Caddy)

### Authentication

Google OAuth with domain restriction. Only users with `@nilenso.com` email addresses can access the dashboard.

**Setup:**
1. Create OAuth credentials at [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Add authorized redirect URI: `https://leavebot.nilenso.com/auth/callback`
3. Configure environment variables (see [Configuration](configuration.md))

**Login Flow:**
1. Visit `/` → Redirected to `/auth/login`
2. Click "Sign in with Google"
3. Authenticate with Google Workspace account
4. Redirected back to dashboard

**Logout:** Click "Logout" in the navigation bar or visit `/auth/logout`

## API Endpoints

### Health Checks

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Overall system health |
| `/api/health/slack` | GET | Slack connection status |
| `/api/health/calendar` | GET | Google Calendar API status |
| `/api/health/harvest` | GET | Harvest API status |

**Example Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-01-06T10:30:00Z",
  "components": {
    "database": {"status": "up", "latency_ms": 5},
    "slack": {"status": "up", "connected": true},
    "calendar": {"status": "up", "latency_ms": 120},
    "harvest": {"status": "up", "latency_ms": 85}
  }
}
```

### Users

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/users` | GET | List all users (paginated) |
| `/api/users` | POST | Create user mapping |
| `/api/users/{id}` | GET | Get user details |
| `/api/users/{id}` | PUT | Update user mapping |
| `/api/users/{id}` | DELETE | Soft-delete user (set inactive) |
| `/api/users/import/slack` | POST | Import users from Slack |
| `/api/users/import/harvest` | POST | Import users from Harvest |

**List Users:**
```bash
GET /api/users?page=1&per_page=20&search=john&active=true
```

Response:
```json
{
  "items": [
    {
      "id": 1,
      "slack_user_id": "U01ABC123",
      "slack_display_name": "John Doe",
      "email": "john@nilenso.com",
      "harvest_user_id": 1234567,
      "slack_timezone": "Asia/Kolkata",
      "is_active": true,
      "created_at": "2026-01-01T00:00:00Z",
      "updated_at": "2026-01-01T00:00:00Z"
    }
  ],
  "total": 24,
  "page": 1,
  "per_page": 20
}
```

**Create User:**
```bash
POST /api/users
Content-Type: application/json

{
  "slack_user_id": "U01ABC123",
  "slack_display_name": "John Doe",
  "email": "john@nilenso.com",
  "harvest_user_id": 1234567
}
```

**Import from Slack:**
```bash
POST /api/users/import/slack
```

Fetches all users from Slack workspace and creates/updates user records.

**Import from Harvest:**
```bash
POST /api/users/import/harvest
```

Fetches all users from Harvest and matches by email to update `harvest_user_id`.

### Leaves

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/leaves` | GET | List leave records (paginated, filtered) |
| `/api/leaves/{id}` | GET | Get leave record details |
| `/api/leaves/{id}` | DELETE | Delete leave record |
| `/api/leaves/{id}/retry` | POST | Retry failed sync |
| `/api/leaves/stats` | GET | Leave statistics |

**List Leaves:**
```bash
GET /api/leaves?page=1&per_page=20&user_id=1&status=completed&from=2026-01-01&to=2026-01-31
```

Response:
```json
{
  "items": [
    {
      "id": 42,
      "user_id": 1,
      "user": {
        "slack_display_name": "John Doe"
      },
      "date": "2026-01-06",
      "leave_type": "full",
      "leave_category": "vacation",
      "status": "completed",
      "calendar_event_id": "abc123...",
      "harvest_entry_id": 98765,
      "created_at": "2026-01-05T14:30:00Z"
    }
  ],
  "total": 47,
  "page": 1,
  "per_page": 20
}
```

**Retry Failed Sync:**
```bash
POST /api/leaves/42/retry
```

Requeues a failed leave record for sync. Returns the updated record.

**Delete Leave:**
```bash
DELETE /api/leaves/42
```

Deletes the leave record and attempts to delete associated:
- Google Calendar event (if exists)
- Harvest time entry (if exists)

**Leave Statistics:**
```bash
GET /api/leaves/stats?year=2026&month=1
```

Response:
```json
{
  "total_days": 47,
  "by_category": {
    "vacation": 40,
    "sick": 7
  },
  "by_user": [
    {"user_id": 1, "name": "John Doe", "days": 5},
    {"user_id": 2, "name": "Jane Doe", "days": 3}
  ]
}
```

### Configuration

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/config` | GET | List all configuration |
| `/api/config/{key}` | GET | Get configuration value |
| `/api/config/{key}` | PUT | Update configuration value |
| `/api/config/{key}` | DELETE | Delete configuration key |

**List Configuration:**
```bash
GET /api/config
```

Response:
```json
{
  "items": [
    {"key": "slack_channel_id", "value": "C0XXXXXXX"},
    {"key": "trigger_keywords", "value": ["leave", "ooo", "sick"]},
    {"key": "default_timezone", "value": "Asia/Kolkata"}
  ]
}
```

**Update Configuration:**
```bash
PUT /api/config/trigger_keywords
Content-Type: application/json

{
  "value": ["leave", "ooo", "sick", "pto", "vacation"]
}
```

## Pydantic Schemas

Location: `leave_bot/web/schemas.py`

### User Schemas

```python
class UserCreate(BaseModel):
    slack_user_id: str
    slack_display_name: str
    email: str | None = None
    harvest_user_id: int | None = None

class UserUpdate(BaseModel):
    slack_display_name: str | None = None
    email: str | None = None
    harvest_user_id: int | None = None
    is_active: bool | None = None

class UserResponse(BaseModel):
    id: int
    slack_user_id: str
    slack_display_name: str
    email: str | None
    harvest_user_id: int | None
    slack_timezone: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
```

### Leave Schemas

```python
class LeaveResponse(BaseModel):
    id: int
    user_id: int
    date: date
    leave_type: LeaveType
    leave_category: LeaveCategory
    status: LeaveStatus
    calendar_event_id: str | None
    harvest_entry_id: int | None
    error_message: str | None
    retry_count: int
    created_at: datetime
    updated_at: datetime
```

## Route Handlers

### Location

```
leave_bot/web/routes/
├── health.py    # Health check endpoints
├── users.py     # User CRUD + import
├── leaves.py    # Leave management
└── config.py    # Configuration CRUD
```

### FastAPI App

Location: `leave_bot/web/app.py`

```python
from fastapi import FastAPI
from leave_bot.web.routes import health, users, leaves, config

app = FastAPI(title="Leave Bot Admin")

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(leaves.router, prefix="/api/leaves", tags=["leaves"])
app.include_router(config.router, prefix="/api/config", tags=["config"])
```

## OpenAPI Documentation

FastAPI automatically generates OpenAPI documentation:

- **Swagger UI**: `/docs`
- **ReDoc**: `/redoc`
- **OpenAPI JSON**: `/openapi.json`

## Error Responses

Standard error response format:

```json
{
  "detail": "User not found"
}
```

HTTP Status Codes:
- `400` - Bad Request (validation error)
- `404` - Not Found
- `409` - Conflict (duplicate record)
- `500` - Internal Server Error

## Running the Web Server

### Standalone

```bash
uv run leave-bot web
```

### With Bot and Worker

```bash
uv run leave-bot all
```

### Docker

```bash
docker compose up web
```

## Related Documentation

- [Configuration](configuration.md) - Environment variables
- [Database](database.md) - Data models
- [Deployment](deployment.md) - Production setup
