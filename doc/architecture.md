# Architecture

System architecture, components, and data flow for the Nilenso Leave Bot.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DigitalOcean Droplet                         │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                      Docker Compose                           │  │
│  │                                                               │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │  │
│  │  │             │  │             │  │                     │   │  │
│  │  │  Slack Bot  │  │  Web Admin  │  │  PostgreSQL         │   │  │
│  │  │  + Worker   │  │  (FastAPI)  │  │                     │   │  │
│  │  │             │  │             │  │                     │   │  │
│  │  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘   │  │
│  │         │                │                    │              │  │
│  │         └────────────────┴────────────────────┘              │  │
│  │                          │                                   │  │
│  │  ┌───────────────────────┴───────────────────────────────┐   │  │
│  │  │                    Shared Services                     │   │  │
│  │  │  • LLM Client (OpenAI)                                │   │  │
│  │  │  • Google Calendar Client                             │   │  │
│  │  │  • Harvest Client                                     │   │  │
│  │  └───────────────────────────────────────────────────────┘   │  │
│  │                                                               │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌───────────────┐                                                  │
│  │    Caddy      │  (Reverse proxy + automatic HTTPS)               │
│  └───────────────┘                                                  │
└─────────────────────────────────────────────────────────────────────┘
          │                    │                     │
          ▼                    ▼                     ▼
    ┌──────────┐        ┌────────────┐        ┌──────────┐
    │  Slack   │        │  Google    │        │ Harvest  │
    │  API     │        │  Calendar  │        │ API      │
    └──────────┘        └────────────┘        └──────────┘
```

## Component Responsibilities

| Component | Responsibility |
|-----------|----------------|
| **Slack Bot** | Socket Mode connection, message listening, confirmation flows, button handling |
| **Worker** | Background processing of confirmed actions, sync orchestration, retry handling |
| **Web Admin** | User management, leave history view, configuration, health dashboard |
| **PostgreSQL** | User mappings, leave records, pending actions, runtime configuration |
| **Caddy** | Reverse proxy for web admin, automatic TLS via Let's Encrypt |

## Tech Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| Language | Python 3.12 | Team familiarity, excellent Slack SDK |
| Slack Integration | slack-bolt | Official framework, handles Socket Mode |
| Web Framework | FastAPI | Async support, automatic OpenAPI docs |
| Database | PostgreSQL 16 | Reliable, good JSON support |
| ORM | SQLAlchemy 2.0 | Async support, type hints, Alembic migrations |
| LLM | OpenAI (configurable) | Structured output for parsing |
| Containerization | Docker + Compose | Simple deployment, reproducible |
| Reverse Proxy | Caddy | Zero-config HTTPS |

## Message Flow

### Leave Creation Flow

```
┌──────────────────────────────────────────────────────────────────┐
│                     Message Event Received                        │
└──────────────────────────────────────────────────────────────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │ Is channel = leave    │───No──▶ Ignore
                    │ channel?              │
                    └───────────────────────┘
                                │ Yes
                                ▼
                    ┌───────────────────────┐
                    │ Contains trigger      │───No──▶ Ignore
                    │ keyword?              │
                    └───────────────────────┘
                                │ Yes
                                ▼
                    ┌───────────────────────┐
                    │ User registered?      │───No──▶ Error message
                    └───────────────────────┘
                                │ Yes
                                ▼
                    ┌───────────────────────┐
                    │ Parse with LLM        │
                    │ (OpenAI structured)   │
                    └───────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
            ┌─────────────┐         ┌─────────────────┐
            │ Valid leave │         │ Not a leave     │
            │ request     │         │ request / Error │
            └─────────────┘         └─────────────────┘
                    │                       │
                    ▼                       ▼
            Create PendingAction          Ignore
                    │
                    ▼
            Send confirmation with buttons
```

### Data Flow Through System

```
Message detected
    → pending_actions INSERT (status='pending', expires_at=now+1hr)
    → [User clicks Confirm] (ack immediately)
    → pending_actions UPDATE (status='confirmed')
    → Worker picks up → pending_actions UPDATE (status='processing')
    → leave_records INSERT (status='confirmed')
    → Calendar API call
    → leave_records UPDATE (calendar_event_id=X)
    → Harvest API call
    → leave_records UPDATE (harvest_entry_id=Y, status='completed')
    → pending_actions UPDATE (status='completed')
    → Update Slack message with success
```

## CLI Entry Points

The `leave-bot` CLI provides multiple entry points:

| Command | Description |
|---------|-------------|
| `leave-bot bot` | Slack bot only (Socket Mode) |
| `leave-bot web` | FastAPI admin server only |
| `leave-bot worker` | Background worker only |
| `leave-bot migrate` | Run Alembic migrations |
| `leave-bot all` | Bot + Worker + Web together |

### Process Architecture

```
leave-bot all
├── asyncio event loop
│   ├── Slack SocketModeHandler
│   │   ├── message.channels events
│   │   └── block_actions (button clicks)
│   ├── Worker loop (polls every 5s)
│   │   ├── Process confirmed actions
│   │   └── Expire old pending actions
│   └── Uvicorn server (FastAPI)
```

## Sync Strategy

### Calendar Events

- **Full-day consecutive leaves** → Single spanning calendar event
- **Half-day leaves** → Individual timed events
- **Mixed leaves** → Grouped appropriately

Example: Leave from Jan 5-7 + half-day Jan 10
```
Calendar Events:
1. "Leave - User" (Jan 5-7, all-day spanning)
2. "Leave - User (AM)" (Jan 10, 11:00-15:00)
```

### Harvest Entries

- Always one entry per day
- Full day = 8 hours
- Half day = 4 hours
- Task selected by category (vacation vs sick)

## Error Handling

### Retry Strategy

| Failure | Handling |
|---------|----------|
| Calendar API error | Retry 3x with backoff, mark as failed |
| Harvest API error | Same as above |
| Partial success | Calendar OK, Harvest failed → keep calendar, mark Harvest failed |
| Rate limiting | Exponential backoff |

### Status Transitions

```
PendingAction:
pending → confirmed → processing → completed
       ↘ cancelled
       ↘ expired

LeaveRecord:
pending → confirmed → completed
                   ↘ failed (retryable)
       ↘ cancelled
```

## Related Documentation

- [Database](database.md) - Data models and schema
- [Slack Bot](slack-bot.md) - Message handling details
- [Integrations](integrations.md) - External service setup
- [Deployment](deployment.md) - Production setup
