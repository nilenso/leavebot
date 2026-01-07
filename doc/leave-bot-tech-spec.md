# Leave Bot Technical Specification

**Project**: Automated Leave Management Bot for nilenso  
**Version**: 1.0 Draft  
**Date**: January 2026  

---

## 1. Overview

### 1.1 Problem Statement

nilenso's leave policy requires employees to:
1. Post a message in the `#wfh-leaves-ooo` Slack channel
2. Mark the leave in the shared Google Calendar ("Leave" calendar)
3. Log 8 hours per day in Harvest under the "Leaves" project

In practice, most people complete step 1 and forget steps 2 and 3, creating tracking inconsistencies.

### 1.2 Solution

A Slack bot that:
- Monitors the leave channel for messages containing leave-related keywords
- Uses an LLM to parse natural language into structured leave data
- Categorizes leave as sick or vacation for Harvest task selection
- Replies in-thread with a confirmation prompt
- Upon confirmation, automatically creates normal calendar events in the "Leave" calendar and Harvest time entries

Additionally, a web admin interface for:
- Managing user mappings (Slack ID ↔ Harvest ID ↔ Email)
- Viewing leave history and sync status
- Manual corrections and configuration

---

## 2. Architecture

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DigitalOcean Droplet                         │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                      Docker Compose                           │  │
│  │                                                               │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │  │
│  │  │             │  │             │  │                     │   │  │
│  │  │  Slack Bot  │  │  Web Admin  │  │  PostgreSQL         │   │  │
│  │  │  (Python)   │  │  (FastAPI)  │  │                     │   │  │
│  │  │             │  │             │  │                     │   │  │
│  │  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘   │  │
│  │         │                │                    │              │  │
│  │         └────────────────┴────────────────────┘              │  │
│  │                          │                                   │  │
│  │  ┌───────────────────────┴───────────────────────────────┐   │  │
│  │  │                    Shared Services                     │   │  │
│  │  │  • LLM Client (OpenAI Responses API)                  │   │  │
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

### 2.2 Component Responsibilities

| Component | Responsibility |
|-----------|----------------|
| **Slack Bot** | Socket Mode connection, message listening, confirmation flows, button handling, background worker loop |
| **Web Admin** | User management UI, leave history view, configuration, health dashboard |
| **PostgreSQL** | User mappings, leave records, pending actions (with dedupe keys) |
| **Caddy** | Reverse proxy for web admin, automatic TLS via Let's Encrypt |

### 2.3 Tech Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| Language | Python 3.12 | Team familiarity, excellent Slack SDK, good LLM libraries |
| Slack Integration | slack-bolt | Official framework, handles Socket Mode, OAuth, events |
| Web Framework | FastAPI | Async support, automatic OpenAPI docs, Pydantic validation |
| Database | PostgreSQL 16 | Reliable, good JSON support for flexible schema |
| ORM | SQLAlchemy 2.0 | Async support, type hints, migrations via Alembic |
| LLM | GPT-5-mini (OpenAI) via Responses API | Structured output with minimal reasoning |
| Task Queue | DB-backed worker loop (single process) | Decouples Slack ack from sync without external queue |
| Containerization | Docker + Docker Compose | Simple deployment, reproducible |
| Reverse Proxy | Caddy | Zero-config HTTPS, simple configuration |

---

## 3. Data Model

### 3.1 Entity Relationship Diagram

```
┌─────────────────────┐       ┌─────────────────────┐
│       users         │       │    leave_records    │
├─────────────────────┤       ├─────────────────────┤
│ id (PK)             │───┐   │ id (PK)             │
│ slack_user_id (UK)  │   │   │ user_id (FK)        │──┐
│ slack_display_name  │   │   │ date                │  │
│ email               │   │   │ leave_type          │  │
│ harvest_user_id     │   │   │ slack_message_ts    │  │
│ slack_timezone      │   │   │ slack_channel_id    │  │
│ is_active           │   │   │ calendar_event_id   │  │
│ created_at          │   │   │ harvest_entry_id    │  │
│ updated_at          │   │   │ leave_category      │  │
└─────────────────────┘   │   │ status              │  │
                          │   │ created_at          │  │
                          │   │ updated_at          │  │
                          │   └─────────────────────┘  │
                          │                            │
                          │   ┌─────────────────────┐  │
                          │   │  pending_actions    │  │
                          │   ├─────────────────────┤  │
                          └──▶│ id (PK)             │  │
                              │ user_id (FK)        │◀─┘
                              │ action_type         │
                              │ payload (JSONB)     │
                              │ slack_event_id      │
                              │ slack_message_ts    │
                              │ slack_channel_id    │
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

### 3.2 Schema Definitions

```sql
-- Users: maps Slack users to Harvest and calendar identities (and caches timezone)
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    slack_user_id VARCHAR(32) UNIQUE NOT NULL,
    slack_display_name VARCHAR(255) NOT NULL,
    email VARCHAR(255),
    harvest_user_id BIGINT,
    slack_timezone VARCHAR(64),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_users_slack_id ON users(slack_user_id);
CREATE INDEX idx_users_harvest_id ON users(harvest_user_id);

-- Leave records: individual leave days (normalized)
CREATE TYPE leave_type AS ENUM ('full', 'half_am', 'half_pm');
CREATE TYPE leave_category AS ENUM ('vacation', 'sick');
CREATE TYPE leave_status AS ENUM (
    'pending',      -- Awaiting user confirmation
    'confirmed',    -- User confirmed, processing
    'completed',    -- Calendar + Harvest synced
    'failed',       -- Sync failed (needs retry/manual)
    'cancelled'     -- User cancelled or retracted
);

CREATE TABLE leave_records (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    date DATE NOT NULL,
    leave_type leave_type NOT NULL DEFAULT 'full',
    leave_category leave_category NOT NULL DEFAULT 'vacation',
    slack_message_ts VARCHAR(32),        -- Original message timestamp
    slack_channel_id VARCHAR(32),
    calendar_event_id VARCHAR(255),      -- Google Calendar event ID
    harvest_entry_id BIGINT,             -- Harvest time entry ID
    status leave_status NOT NULL DEFAULT 'pending',
    error_message TEXT,                  -- If status = 'failed'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(user_id, date)  -- One record per user per day
);

CREATE INDEX idx_leave_records_user_date ON leave_records(user_id, date);
CREATE INDEX idx_leave_records_status ON leave_records(status);

-- Pending actions: temporary storage for confirmation flow
CREATE TYPE action_type AS ENUM ('create_leave', 'cancel_leave');
CREATE TYPE action_status AS ENUM (
    'pending',
    'confirmed',
    'processing',
    'completed',
    'expired',
    'cancelled'
);

CREATE TABLE pending_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL REFERENCES users(id),
    action_type action_type NOT NULL,
    payload JSONB NOT NULL,              -- Parsed leave data from LLM
    slack_event_id VARCHAR(64),          -- Slack Events API event_id (for dedupe)
    slack_message_ts VARCHAR(32),        -- Bot's confirmation message
    slack_channel_id VARCHAR(32),
    slack_thread_ts VARCHAR(32),         -- Original user's message (thread parent)
    expires_at TIMESTAMPTZ NOT NULL,     -- Auto-expire after 1 hour
    status action_status NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_pending_actions_status ON pending_actions(status, expires_at);
CREATE UNIQUE INDEX idx_pending_actions_event_id
    ON pending_actions(slack_event_id)
    WHERE slack_event_id IS NOT NULL;

-- Configuration: runtime settings
CREATE TABLE configuration (
    key VARCHAR(255) PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Pre-populate with defaults
INSERT INTO configuration (key, value) VALUES
    ('slack_channel_id', '"C0XXXXXXX"'),
    ('harvest_leaves_project_id', 'null'),
    ('harvest_vacation_task_id', 'null'),
    ('harvest_sick_task_id', 'null'),
    ('calendar_id', '"leave@group.calendar.google.com"'),
    ('trigger_keywords', '["leave", "off", "ooo", "pto", "vacation", "sick"]'),
    ('confirmation_timeout_minutes', '60'),
    ('default_timezone', '"Asia/Kolkata"');

-- Half-day time windows are fixed constants in v1 (11:00-15:00 and 15:00-19:00, user's timezone).

```

### 3.3 Key Data Flows

**Leave Creation Flow:**
```
Message detected
    → pending_actions INSERT (status='pending', expires_at=now+1hr, slack_event_id=event_id)
    → [User clicks Confirm] (ack immediately)
    → pending_actions UPDATE (status='confirmed')
    → Worker picks confirmed action → pending_actions UPDATE (status='processing')
    → leave_records INSERT (status='confirmed')
    → Calendar API call
    → leave_records UPDATE (calendar_event_id=X)
    → Harvest API call (task selected by category)
    → leave_records UPDATE (harvest_entry_id=Y, status='completed')
    → pending_actions UPDATE (status='completed')
```

---

## 4. Slack Bot Design

### 4.1 Event Flow

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
                    │ Is user in users      │───No──▶ Reply: "You're not 
                    │ table?                │        registered. Contact admin."
                    └───────────────────────┘
                                │ Yes
                                ▼
                    ┌───────────────────────┐
                    │ Parse with LLM        │
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
            ┌─────────────┐               Ignore
            │ Check for   │               (silently)
            │ conflicts   │
            └─────────────┘
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
┌─────────────┐         ┌─────────────────┐
│ No conflict │         │ Has conflict    │
└─────────────┘         └─────────────────┘
        │                       │
        ▼                       ▼
┌─────────────┐         ┌─────────────────────┐
│ Store       │         │ Reply with conflict │
│ pending     │         │ warning + confirm   │
│ action      │         │ anyway option       │
└─────────────┘         └─────────────────────┘
        │
        ▼
┌─────────────────────────────────────────┐
│ Reply in thread with confirmation       │
│ buttons: [✓ Confirm] [✗ Cancel]         │
└─────────────────────────────────────────┘
```

**Thread replies:**
- Process thread replies only when they are replies to a bot prompt (confirmation/clarification/cancellation).
- Ignore other threaded messages; top-level channel messages remain the primary trigger.
- Thread replies bypass the keyword filter (the thread context is the signal).

### 4.2 Slack App Configuration

**Required Bot Token Scopes:**
- `channels:history` - Read messages in public channels
- `channels:read` - View basic channel info
- `chat:write` - Send messages
- `users:read` - Get user info (display names)
- `reactions:write` - Add reactions (optional, for acknowledgment)

**Event Subscriptions:**
- `message.channels` - Messages in public channels

**Interactivity:**
- Enable for button handling (Socket Mode handles this automatically)

**Socket Mode:**
- Enabled (no public URL required)
- App-level token with `connections:write` scope

### 4.3 Message Parsing Specification

**LLM System Prompt:**
```
You are a leave request parser for a workplace Slack channel. Extract structured 
leave information from natural language messages.

User timezone: {user_timezone}
Today's date (in user's timezone): {current_date}
Current day of week (in user's timezone): {current_day}

RULES:
1. Parse relative dates ("tomorrow", "next Monday", "the 5th") into absolute dates
2. Identify leave type: full day, half day (morning), half day (afternoon)
3. Handle date ranges ("5th to 10th" = 6 days)
4. Categorize leave as "sick" or "vacation" based on wording
5. Detect cancellations ("cancelled my leave", "not taking leave anymore")
6. Return is_leave_request: false if the message is just casual mention of "leave"
   or discussion about leave policy, not an actual leave request
7. Handle multi-day leaves with different types (e.g., "half day today, full day tomorrow")
8. Ignore WFH requests (not tracked); return is_leave_request: false
9. Ignore public holiday requests (not tracked); return is_leave_request: false

OUTPUT FORMAT (JSON only, no explanation):
{
  "is_leave_request": boolean,
  "is_cancellation": boolean,
  "confidence": "high" | "medium" | "low",
  "dates": [
    {
      "date": "YYYY-MM-DD",
      "type": "full" | "half_am" | "half_pm",
      "category": "vacation" | "sick"
    }
  ],
  "original_text_summary": "brief human-readable summary",
  "ambiguity_notes": "string or null - note any ambiguities"
}

**Schema validation:**
- Use the LLM's structured output / JSON schema mode where available.
- Validate against a strict schema (Pydantic). If invalid, ask the user to clarify.

EXAMPLES:

Input: "marking tomorrow as leave"
Output: {"is_leave_request": true, "is_cancellation": false, "confidence": "high", 
         "dates": [{"date": "2026-01-03", "type": "full", "category": "vacation"}], 
         "original_text_summary": "Full day leave tomorrow",
         "ambiguity_notes": null}

Input: "taking the second half of today off.. Grandfather's birthday"
Output: {"is_leave_request": true, "is_cancellation": false, "confidence": "high",
         "dates": [{"date": "2026-01-02", "type": "half_pm", "category": "vacation"}],
         "original_text_summary": "Half day (afternoon) today",
         "ambiguity_notes": null}

Input: "down with fever today"
Output: {"is_leave_request": true, "is_cancellation": false, "confidence": "high",
         "dates": [{"date": "2026-01-02", "type": "full", "category": "sick"}],
         "original_text_summary": "Sick leave today",
         "ambiguity_notes": null}

Input: "Will be on leave today & on 2nd. 1st is exotel holiday"
Output: {"is_leave_request": true, "is_cancellation": false, "confidence": "high",
         "dates": [{"date": "2026-01-01", "type": "full", "category": "vacation"}, {"date": "2026-01-02", "type": "full", "category": "vacation"}],
         "original_text_summary": "Full day leave on 1st and 2nd January",
         "ambiguity_notes": null}

Input: "I have cancelled my leave. Going to office."
Output: {"is_leave_request": false, "is_cancellation": true, "confidence": "high",
         "dates": [],
         "original_text_summary": "Cancellation of previously announced leave",
         "ambiguity_notes": "No specific dates mentioned for cancellation"}

Input: "can someone explain the leave policy?"
Output: {"is_leave_request": false, "is_cancellation": false, "confidence": "high",
         "dates": [],
         "original_text_summary": "Not a leave request",
         "ambiguity_notes": null}

Input: "will be taking leave from 5th to 10th"  
Output: {"is_leave_request": true, "is_cancellation": false, "confidence": "high",
         "dates": [
           {"date": "2026-01-05", "type": "full", "category": "vacation"},
           {"date": "2026-01-06", "type": "full", "category": "vacation"},
           {"date": "2026-01-07", "type": "full", "category": "vacation"},
           {"date": "2026-01-08", "type": "full", "category": "vacation"},
           {"date": "2026-01-09", "type": "full", "category": "vacation"},
           {"date": "2026-01-10", "type": "full", "category": "vacation"}
         ],
         "original_text_summary": "6 days leave from Jan 5-10",
         "ambiguity_notes": null}
```

**Confidence Handling:**
- `high`: Proceed with confirmation
- `medium`: Proceed but include note in confirmation message
- `low`: Reply asking for clarification instead of confirmation

**Category guidance:**
- Treat keywords like "sick", "fever", "flu", "unwell", "doctor", "hospital" as `sick`.
- If not clearly sick-related, default to `vacation`. If unsure, set `confidence` to `medium` and note ambiguity.

**Post-parse validation:**
- Use the Slack user's timezone for relative date resolution; fall back to `default_timezone` if missing.
- Reject dates earlier than Jan 1 of the current year (based on user's timezone) and ask the user to contact admin for older retroactive entries.

### 4.4 Confirmation Message Design

```
┌────────────────────────────────────────────────────────────┐
│ 📅 I'll record the following leave for you:                │
│                                                            │
│ • Friday, Jan 3, 2026 — Full day (Vacation)               │
│ • Monday, Jan 6, 2026 — Full day (Vacation)               │
│                                                            │
│ This will:                                                 │
│ • Create normal events in the Leave calendar              │
│ • Log 8 hours per full day (4 for half) in Harvest        │
│                                                            │
│ ┌─────────────┐  ┌─────────────┐                          │
│ │ ✓ Confirm   │  │ ✗ Cancel    │                          │
│ └─────────────┘  └─────────────┘                          │
└────────────────────────────────────────────────────────────┘
```

**With conflict warning:**
```
┌────────────────────────────────────────────────────────────┐
│ ⚠️ You already have leave recorded for Jan 3, 2026.        │
│                                                            │
│ I'll record the following NEW leave:                       │
│ • Monday, Jan 6, 2026 — Full day (Vacation)               │
│                                                            │
│ ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│ │ ✓ Confirm   │  │ ✗ Cancel    │  │ ⚠ Override existing │ │
│ └─────────────┘  └─────────────┘  └─────────────────────┘ │
└────────────────────────────────────────────────────────────┘
```

### 4.5 Button Action Handlers

| Action ID | Behavior |
|-----------|----------|
| `leave_confirm` | Ack immediately, mark pending action confirmed; worker performs sync and updates message |
| `leave_cancel` | Ack immediately, mark pending action cancelled, update message to cancelled |
| `leave_override` | Ack immediately, mark confirmed with override flag; worker deletes existing records then syncs |

### 4.6 Async Processing, Dedupe, Expiry

- **Ack fast:** Slack events and button actions are acknowledged immediately; all slow work is moved to a DB-backed worker loop.
- **Worker loop (simple):** A single process polls `pending_actions` in `confirmed` status, marks them `processing`, executes sync, then marks `completed`. It also retries `leave_records` in `failed` status with backoff.
- **Dedupe strategy:** Store `slack_event_id` from Slack Events API in `pending_actions` and enforce a unique index. If an insert conflicts, treat it as a retry and no-op. Action retries are handled idempotently by checking `pending_actions.status` before work.
- **Expiry sweeper:** The same worker loop periodically marks expired actions as `expired` and updates the Slack message to disable buttons.

---

## 5. Web Admin Interface

### 5.1 Routes & Pages

| Route | Page | Description |
|-------|------|-------------|
| `/` | Dashboard | Health status, recent activity (minimal) |
| `/users` | User List | All mapped users with search/filter |
| `/users/new` | Add User | Form to add new user mapping |
| `/users/{id}` | Edit User | Edit existing user mapping |
| `/users/import` | Bulk Import | Import users from Slack/Harvest |
| `/leaves` | Leave History | Paginated list of all leave records |
| `/leaves/{id}` | Leave Detail | Single record with sync status, retry options |
| `/config` | Configuration | Edit runtime settings |

### 5.2 API Endpoints

```
# Users
GET    /api/users                    List all users (paginated)
POST   /api/users                    Create user mapping
GET    /api/users/{id}               Get user details
PUT    /api/users/{id}               Update user mapping
DELETE /api/users/{id}               Soft-delete user (set inactive)
POST   /api/users/import/slack       Import users from Slack workspace
POST   /api/users/import/harvest     Import users from Harvest

# Leaves  
GET    /api/leaves                   List leave records (paginated, filtered)
GET    /api/leaves/{id}              Get leave record details
POST   /api/leaves/{id}/retry        Retry failed sync
DELETE /api/leaves/{id}              Delete leave record (and sync deletions)

# Configuration
GET    /api/config                   Get all configuration
PUT    /api/config/{key}             Update configuration value

# Health
GET    /api/health                   Health check (DB, Slack, Calendar, Harvest)
GET    /api/health/slack             Test Slack connection
GET    /api/health/calendar          Test Calendar connection  
GET    /api/health/harvest           Test Harvest connection
```

### 5.3 Authentication

For v1, use the simplest option: **Caddy HTTP Basic Auth** only (single shared password).
- No app-level auth in the FastAPI app.
- Rotate by updating `ADMIN_PASSWORD_HASH` and restarting Caddy.

### 5.4 UI Wireframes

**Dashboard:**
```
┌─────────────────────────────────────────────────────────────────┐
│  Leave Bot Admin                              [Health: ✓ OK]    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ Users        │  │ This Month   │  │ Pending      │          │
│  │     24       │  │    47 days   │  │     3        │          │
│  │   mapped     │  │   of leave   │  │   actions    │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                 │
│  Recent Activity                                                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 10:30  Raj confirmed leave for Jan 3                    │   │
│  │ 10:25  Yogi's leave synced: Calendar ✓ Harvest ✓        │   │
│  │ 09:15  Pavithra confirmed half-day for Jan 2            │   │
│  │ 09:10  ⚠️ Failed to sync Atharva's leave - retrying     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  [Users]  [Leave History]  [Configuration]                     │
└─────────────────────────────────────────────────────────────────┘
```

**User Management:**
```
┌─────────────────────────────────────────────────────────────────┐
│  Users                                    [+ Add User] [Import] │
├─────────────────────────────────────────────────────────────────┤
│  Search: [________________]  Filter: [All ▼]                    │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Name              │ Slack ID    │ Harvest ID │ Status   │   │
│  ├───────────────────┼─────────────┼────────────┼──────────┤   │
│  │ Atharva Raykar    │ U01ABC123   │ 1234567    │ ✓ Active │   │
│  │ Kiran Rao         │ U01DEF456   │ 1234568    │ ✓ Active │   │
│  │ Neena S           │ U01GHI789   │ 1234569    │ ✓ Active │   │
│  │ Raj Kumar         │ U01JKL012   │ —          │ ⚠ Incomplete│ │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Showing 1-20 of 24                          [< Prev] [Next >]  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. External Integrations

### 6.1 Google Calendar

**Authentication:** Service Account with domain-wide delegation (or calendar sharing)

**Setup Requirements:**
1. Create GCP project
2. Enable Google Calendar API
3. Create Service Account
4. Download JSON key file
5. Share "Leave" calendar with service account email (Editor permission)

**Event Type:** Create normal events in the "Leave" calendar (eventType `default`), not out-of-office/leave event types.

**Event Creation:**
```python
event = {
    'summary': f'Leave - {user_name}',
    'description': f'Auto-created by Leave Bot\nSlack message: {message_link}',
    'start': {'date': '2026-01-03'},  # All-day event
    'end': {'date': '2026-01-04'},    # End date is exclusive in Google Calendar
    'eventType': 'default',           # Normal event (not outOfOffice)
}
```

**For half-days:**
```python
# Morning half (11 AM - 3 PM, fixed window in user's timezone)
event = {
    'summary': f'Leave - {user_name} (AM)',
    'start': {'dateTime': '2026-01-03T11:00:00', 'timeZone': user_timezone},
    'end': {'dateTime': '2026-01-03T15:00:00', 'timeZone': user_timezone},
}

# Afternoon half (3 PM - 7 PM, fixed window in user's timezone)
event = {
    'summary': f'Leave - {user_name} (PM)',
    'start': {'dateTime': '2026-01-03T15:00:00', 'timeZone': user_timezone},
    'end': {'dateTime': '2026-01-03T19:00:00', 'timeZone': user_timezone},
}
```

### 6.2 Harvest

**Authentication:** Personal Access Token (for single-org use) or OAuth2

**Setup Requirements:**
1. Create Personal Access Token at https://id.getharvest.com/developers
2. Note Account ID
3. Identify the "Leaves" client/project IDs and task IDs

**Harvest Structure:**
```
Client: Leaves
├── Personal leave / vacation  ← Default for vacation category
├── Public holiday             ← Ignored in v1
└── Sick leaves                ← Used for sick category
```

The bot will log leave to "Personal leave / vacation" or "Sick leaves" based on the parsed category. Public holiday is not handled in v1.

**Time Entry Creation:**
```python
payload = {
    'user_id': harvest_user_id,
    'project_id': LEAVES_PROJECT_ID,        # The "Leaves" project
    'task_id': VACATION_LEAVE_TASK_ID if category == "vacation" else SICK_LEAVE_TASK_ID,
    'spent_date': '2026-01-03',
    'hours': 8.0,  # or 4.0 for half-day
    'notes': 'Leave (auto-logged from Slack)'
}

headers = {
    'Authorization': f'Bearer {ACCESS_TOKEN}',
    'Harvest-Account-Id': ACCOUNT_ID,
    'User-Agent': 'NilensoLeaveBot (contact@nilenso.com)',
    'Content-Type': 'application/json'
}

response = requests.post(
    'https://api.harvestapp.com/v2/time_entries',
    json=payload,
    headers=headers
)
```

**Important:** The token must have admin permissions to create entries for other users.

### 6.3 OpenAI Responses API (LLM)

**Model:** `gpt-5-mini` with reasoning effort set to `minimal`

**Integration:** Use the OpenAI Responses API (Python SDK) with structured outputs and schema validation.

**Reasoning config:** Set reasoning effort to `minimal` via the Responses API reasoning config (required by policy here).

**Rate Limits:** Comfortable headroom for a small org's leave messages

**Cost Estimate:** Low volume; depends on OpenAI pricing.

---

## 7. Deployment

### 7.1 Directory Structure

```
leave-bot/
├── docker-compose.yml
├── Dockerfile
├── Caddyfile
├── .env.example
├── alembic.ini
├── alembic/
│   └── versions/
├── src/
│   ├── __init__.py
│   ├── main.py                 # Entry point
│   ├── config.py               # Settings via pydantic-settings
│   ├── database.py             # SQLAlchemy setup
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── leave.py
│   │   └── pending_action.py
│   ├── bot/
│   │   ├── __init__.py
│   │   ├── app.py              # Slack Bolt app
│   │   ├── handlers.py         # Message & action handlers
│   │   ├── parser.py           # LLM parsing logic
│   │   └── blocks.py           # Block Kit message builders
│   ├── services/
│   │   ├── __init__.py
│   │   ├── calendar.py         # Google Calendar client
│   │   ├── harvest.py          # Harvest client
│   │   └── sync.py             # Orchestrates the sync
│   ├── web/
│   │   ├── __init__.py
│   │   ├── app.py              # FastAPI app
│   │   ├── auth.py             # Authentication
│   │   ├── routes/
│   │   │   ├── users.py
│   │   │   ├── leaves.py
│   │   │   └── config.py
│   │   └── templates/          # Jinja2 templates (if SSR)
│   └── utils/
│       ├── __init__.py
│       └── dates.py            # Date parsing helpers
└── tests/
    ├── conftest.py
    ├── test_parser.py
    ├── test_handlers.py
    └── test_sync.py
```

### 7.2 Docker Configuration

**Dockerfile:**
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Create non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Default command (can be overridden in docker-compose)
CMD ["python", "-m", "src.main"]
```

**docker-compose.yml:**
```yaml
version: '3.8'

services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: leavebot
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: leavebot
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U leavebot"]
      interval: 5s
      timeout: 5s
      retries: 5

  bot:
    build: .
    command: python -m src.main bot
    environment:
      DATABASE_URL: postgresql://leavebot:${DB_PASSWORD}@db:5432/leavebot
      SLACK_BOT_TOKEN: ${SLACK_BOT_TOKEN}
      SLACK_APP_TOKEN: ${SLACK_APP_TOKEN}
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      GOOGLE_SERVICE_ACCOUNT_JSON: ${GOOGLE_SERVICE_ACCOUNT_JSON}
      HARVEST_ACCESS_TOKEN: ${HARVEST_ACCESS_TOKEN}
      HARVEST_ACCOUNT_ID: ${HARVEST_ACCOUNT_ID}
    depends_on:
      db:
        condition: service_healthy
    restart: unless-stopped

  web:
    build: .
    command: uvicorn src.web.app:app --host 0.0.0.0 --port 8000
    environment:
      DATABASE_URL: postgresql://leavebot:${DB_PASSWORD}@db:5432/leavebot
      # Include other env vars as needed for health checks
      SLACK_BOT_TOKEN: ${SLACK_BOT_TOKEN}
      HARVEST_ACCESS_TOKEN: ${HARVEST_ACCESS_TOKEN}
      HARVEST_ACCOUNT_ID: ${HARVEST_ACCOUNT_ID}
    depends_on:
      db:
        condition: service_healthy
    restart: unless-stopped

  caddy:
    image: caddy:2-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      - web
    restart: unless-stopped

volumes:
  postgres_data:
  caddy_data:
  caddy_config:
```

**Caddyfile:**
```
leavebot.nilenso.com {
    reverse_proxy web:8000
    
    # Basic auth (single shared password)
    basicauth /* {
        admin {$ADMIN_PASSWORD_HASH}
    }
}
```

### 7.3 Environment Variables

**.env.example:**
```bash
# Database
DB_PASSWORD=change-me-to-strong-password

# Slack
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
SLACK_SIGNING_SECRET=your-signing-secret

# OpenAI
OPENAI_API_KEY=sk-openai-your-key

# Google Calendar (base64 encoded JSON)
GOOGLE_SERVICE_ACCOUNT_JSON=eyJhbGciOiJSUzI1NiIs...

# Harvest
HARVEST_ACCESS_TOKEN=your-harvest-token
HARVEST_ACCOUNT_ID=123456

# Web Admin
ADMIN_PASSWORD_HASH=$2a$14$... # bcrypt hash for Caddy

# Configuration (can also be set in DB)
LEAVE_CHANNEL_ID=C0XXXXXXX
LEAVES_PROJECT_ID=12345678
VACATION_LEAVE_TASK_ID=87654321
SICK_LEAVE_TASK_ID=87654322
CALENDAR_ID=leave@group.calendar.google.com
DEFAULT_TIMEZONE=Asia/Kolkata
```

### 7.4 DigitalOcean Deployment Steps

1. **Create Droplet:**
   - Ubuntu 24.04 LTS
   - Basic: 1 vCPU, 1GB RAM ($6/mo) — sufficient for this workload
   - Enable backups

2. **Initial Setup:**
```bash
# SSH into droplet
ssh root@your-droplet-ip

# Create non-root user
adduser deploy
usermod -aG sudo deploy

# Install Docker
curl -fsSL https://get.docker.com | sh
usermod -aG docker deploy

# Install Docker Compose
apt install docker-compose-plugin

# Clone repo
su - deploy
git clone https://github.com/nilenso/leave-bot.git
cd leave-bot

# Configure environment
cp .env.example .env
nano .env  # Fill in all values

# Start services
docker compose up -d

# Run migrations
docker compose exec bot alembic upgrade head
```

3. **DNS Configuration:**
   - Point `leavebot.nilenso.com` (or similar) A record to droplet IP
   - Caddy will automatically obtain Let's Encrypt certificate

4. **Monitoring (optional):**
   - Set up DigitalOcean monitoring alerts for CPU/memory
   - Consider adding Sentry for error tracking

---

## 8. Edge Cases & Error Handling

### 8.1 Message Parsing Edge Cases

| Scenario | Handling |
|----------|----------|
| **Ambiguous dates** ("on the 5th" — which month?) | Assume current month; if date passed, assume next month |
| **Past dates** ("was on leave yesterday") | Allow only back to Jan 1 of the current year; older requests require admin help |
| **Far future dates** ("leave in March") | Allow but flag in confirmation |
| **Vague messages** ("might take leave") | LLM returns `is_leave_request: false` |
| **Multiple leaves in one message** | Parse all, create multiple records |
| **Message edits** | Ignored; user must cancel and re-post |
| **Threaded messages** | Accepted only when replying to a bot prompt; otherwise ignored |
| **@mentions in message** | Strip before parsing, but preserve for context |
| **WFH messages** | Ignored (WFH not tracked) |
| **Public holiday requests** | Ignored (not handled in v1) |
| **Category unclear** | Default to vacation and include a note in confirmation |

### 8.2 Conflict Scenarios

| Scenario | Handling |
|----------|----------|
| **Duplicate leave same day** | Detect, offer to override or skip |
| **Overlapping with existing Harvest entry** | Check before creating, warn user |
| **User not in Harvest** | Create calendar event only, warn about Harvest skip |
| **Calendar event exists (manual entry)** | Create anyway (duplicates are user's responsibility) |

### 8.3 Sync Failures

| Failure | Handling |
|---------|----------|
| **Calendar API error** | Retry 3x with backoff, mark as failed, admin can retry |
| **Harvest API error** | Same as above |
| **Partial success** (Calendar OK, Harvest failed) | Mark status appropriately, don't rollback calendar |
| **Rate limiting** | Implement exponential backoff |
| **Token expiry** | Refresh tokens (OAuth2) or alert admin (PAT) |

### 8.4 User Experience Edge Cases

| Scenario | Handling |
|----------|----------|
| **User clicks confirm twice** | Idempotent — second click shows "already processed" |
| **Confirmation expires** | Worker marks expired after 1 hour, disables buttons, updates message |
| **User deletes their message** | Pending action orphaned, expires naturally |
| **Bot message deleted** | Pending action orphaned, expires naturally |
| **User cancels then wants to re-confirm** | Must post new message |
| **Weekend/holiday detection** | Optional warning ("Jan 4 is Saturday, confirm?") |

### 8.5 Cancellation Handling

When user says "I cancelled my leave":

1. LLM detects `is_cancellation: true`
2. If specific dates mentioned in the cancellation message:
   - Look up those dates in leave_records
   - Offer to delete calendar events and Harvest entries
3. If no specific dates mentioned:
   - Reply asking for clarification in-thread: "Which dates would you like to cancel?"

```
┌────────────────────────────────────────────────────────────┐
│ 🔄 Which leave dates would you like to cancel?             │
│                                                            │
│ Please reply in this thread with the specific dates,      │
│ e.g., "cancel my leave on Jan 3" or "cancel Jan 3-5"       │
└────────────────────────────────────────────────────────────┘
```

When dates are specified:
```
┌────────────────────────────────────────────────────────────┐
│ 🔄 I'll cancel your leave for:                            │
│                                                            │
│ • Friday, Jan 3, 2026                                     │
│                                                            │
│ This will delete the calendar event and Harvest entry.    │
│                                                            │
│ ┌─────────────────────┐  ┌─────────────────┐              │
│ │ ✓ Yes, cancel       │  │ ✗ Keep it       │              │
│ └─────────────────────┘  └─────────────────┘              │
└────────────────────────────────────────────────────────────┘
```

---

## 9. Testing Strategy

### 9.1 Unit Tests

| Component | Test Focus |
|-----------|------------|
| `parser.py` | LLM prompt produces correct structured output for various inputs |
| `blocks.py` | Block Kit JSON is valid and renders correctly |
| `dates.py` | Relative date parsing works across edge cases |
| `sync.py` | Sync logic handles success/failure states correctly |

### 9.2 Integration Tests

| Test | Setup |
|------|-------|
| **Database operations** | Use testcontainers for PostgreSQL |
| **Slack message handling** | Mock Slack client, verify correct responses |
| **Full sync flow** | Mock Calendar + Harvest APIs, verify records created |

### 9.3 Manual Testing Checklist

- [ ] Post leave message → confirmation appears in thread
- [ ] Click confirm → calendar event visible, Harvest entry visible
- [ ] Click cancel → no external changes
- [ ] Post ambiguous message → clarification requested
- [ ] Reply in thread to clarification → parsed and confirmed
- [ ] Post non-leave message with trigger word → ignored
- [ ] Unregistered user posts → helpful error message
- [ ] Post cancellation → appropriate handling
- [ ] Expire a pending action → buttons disabled
- [ ] Post leave before Jan 1 of current year → rejected with guidance
- [ ] Post sick leave message → Harvest entry uses "Sick leaves" task
- [ ] Web admin: add user, view leaves, retry failed sync

---

## 10. Monitoring & Observability

### 10.1 Health Checks

**Endpoint:** `GET /api/health`

```json
{
  "status": "healthy",
  "timestamp": "2026-01-02T10:30:00Z",
  "components": {
    "database": {"status": "up", "latency_ms": 5},
    "slack": {"status": "up", "connected": true},
    "calendar": {"status": "up", "latency_ms": 120},
    "harvest": {"status": "up", "latency_ms": 85}
  }
}
```

### 10.2 Metrics to Track

| Metric | Purpose |
|--------|---------|
| `leave_messages_processed` | Volume tracking |
| `leave_confirmations` | Successful syncs |
| `leave_cancellations` | User-cancelled |
| `sync_failures` | Reliability tracking |
| `llm_parse_time` | LLM latency |
| `calendar_api_time` | External API latency |
| `harvest_api_time` | External API latency |

### 10.3 Alerting

Set up alerts for:
- Bot disconnected from Slack (Socket Mode connection lost)
- Sync failure rate > 10% in 1 hour
- Pending actions not being processed (queue growing)
- External API consistently failing

### 10.4 Logging

```python
import structlog

log = structlog.get_logger()

# In handlers
log.info("leave_message_received", 
         user_id=user_id, 
         channel=channel,
         message_preview=text[:50])

log.info("leave_confirmed",
         user_id=user_id,
         dates=[d["date"] for d in parsed["dates"]],
         calendar_event_id=calendar_result.get("id"),
         harvest_entry_id=harvest_result.get("id"))

log.error("harvest_sync_failed",
          user_id=user_id,
          error=str(e),
          will_retry=True)
```

---

## 11. Future Enhancements (v2+)

| Feature | Description | Effort |
|---------|-------------|--------|
| **Leave category selection** | Allow users to pick Vacation/Sick explicitly | Low |
| **Slack OAuth for admin** | Secure admin access with Slack SSO | Medium |
| **Leave balance tracking** | Track annual leave allocation and usage (integrates with "33 days" limit) | High |
| **Manager notifications** | Notify manager when report takes leave | Low |
| **Calendar integration** | Detect calendar conflicts before confirming | Medium |
| **Harvest project auto-detect** | If user is on a client, log to client's project | Medium |
| **Weekly digest** | Summary of team leave for the week | Low |
| **Public holidays** | Auto-detect and skip public holidays | Medium |
| **Slack reminders** | "You mentioned leave but didn't confirm" after 24h | Low |
| **Multi-workspace** | Support multiple Slack workspaces (if needed) | High |

---

## 12. Security Considerations

| Concern | Mitigation |
|---------|------------|
| **Secrets in env vars** | Use `.env` file, not committed; consider secrets manager for prod |
| **API token exposure** | Never log tokens; use environment variables |
| **Admin interface access** | HTTPS only (Caddy), basic auth minimum |
| **Database access** | Not exposed publicly; only accessible within Docker network |
| **Slack verification** | Bolt handles signing secret verification automatically |
| **SQL injection** | SQLAlchemy ORM with parameterized queries |
| **XSS in admin UI** | Jinja2 auto-escaping; or React for SPA |

---

## 13. Estimated Timeline

| Phase | Tasks | Duration |
|-------|-------|----------|
| **Setup** | Slack app config, GCP project, Harvest token, Docker setup | 1 day |
| **Core bot** | Message listener, LLM parser, confirmation flow | 2-3 days |
| **Sync logic** | Calendar integration, Harvest integration | 2 days |
| **Database & models** | Schema, migrations, CRUD operations | 1 day |
| **Web admin (basic)** | User CRUD, leave list, health dashboard | 2-3 days |
| **Testing & polish** | Unit tests, manual testing, bug fixes | 2 days |
| **Deployment** | DigitalOcean setup, DNS, monitoring | 1 day |
| **Documentation** | README, runbook, user guide | 1 day |
| **Buffer** | Unexpected issues, scope creep | 2 days |

**Total estimate:** 2-3 weeks for a solid v1

---

## 14. Design Decisions (Resolved)

| Question | Decision |
|----------|----------|
| **Half-day times** | Fixed to 11 AM - 3 PM (morning), 3 PM - 7 PM (afternoon) in user's timezone (not configurable in v1) |
| **Harvest project structure** | Client "Leaves" with tasks: Personal leave/vacation, Public holiday (ignored), Sick leaves |
| **Leave categories** | Vacation or Sick (maps to Harvest tasks); public holiday ignored in v1 |
| **User onboarding** | Admin-only via web interface |
| **Retroactive logging** | Allowed back to Jan 1 of the current year only |
| **Web admin auth** | Caddy HTTP Basic Auth (no app-level auth) |
| **Message edits** | Ignored (user must cancel and re-post) |
| **Cancellation ambiguity** | Ask for clarification, don't auto-detect context |
| **Client notifications** | Out of scope for v1 |
| **Public holidays** | Not handled in v1 |
| **Thread replies** | Accepted when replying to bot prompts |
| **WFH handling** | Ignored (not tracked) |
| **Timezone** | Use Slack user's timezone for relative date parsing and half-day windows |

---

## Appendix A: Sample LLM Test Cases

```python
TEST_CASES = [
    # Basic cases
    ("marking tomorrow as leave", {"dates": [{"date": "2026-01-03", "type": "full", "category": "vacation"}]}),
    ("on leave today", {"dates": [{"date": "2026-01-02", "type": "full", "category": "vacation"}]}),
    ("taking day off", {"dates": [{"date": "2026-01-02", "type": "full", "category": "vacation"}]}),
    ("down with fever today", {"dates": [{"date": "2026-01-02", "type": "full", "category": "sick"}]}),
    
    # Half days
    ("taking first half off", {"dates": [{"date": "2026-01-02", "type": "half_am", "category": "vacation"}]}),
    ("second half of today off", {"dates": [{"date": "2026-01-02", "type": "half_pm", "category": "vacation"}]}),
    ("half day in the morning", {"dates": [{"date": "2026-01-02", "type": "half_am", "category": "vacation"}]}),
    ("afternoon off", {"dates": [{"date": "2026-01-02", "type": "half_pm", "category": "vacation"}]}),
    
    # Specific dates
    ("leave on 15th", {"dates": [{"date": "2026-01-15", "type": "full", "category": "vacation"}]}),
    ("off on Jan 20", {"dates": [{"date": "2026-01-20", "type": "full", "category": "vacation"}]}),
    ("leave on 2026-01-25", {"dates": [{"date": "2026-01-25", "type": "full", "category": "vacation"}]}),
    
    # Ranges
    ("leave from 5th to 7th", {"dates": [
        {"date": "2026-01-05", "type": "full", "category": "vacation"},
        {"date": "2026-01-06", "type": "full", "category": "vacation"},
        {"date": "2026-01-07", "type": "full", "category": "vacation"},
    ]}),
    ("off Mon to Wed next week", {"dates": [...]}),  # 3 days
    
    # Multiple discrete days
    ("leave on 5th and 10th", {"dates": [
        {"date": "2026-01-05", "type": "full", "category": "vacation"},
        {"date": "2026-01-10", "type": "full", "category": "vacation"},
    ]}),
    
    # Cancellations
    ("cancelled my leave", {"is_cancellation": True, "dates": []}),
    ("not taking leave anymore", {"is_cancellation": True, "dates": []}),
    ("scratch that, coming to office", {"is_cancellation": True, "dates": []}),
    
    # Not leave requests
    ("can someone explain leave policy?", {"is_leave_request": False}),
    ("how many leaves do I have?", {"is_leave_request": False}),
    ("leave me alone", {"is_leave_request": False}),
    ("nice work, take off!", {"is_leave_request": False}),
    ("wfh today", {"is_leave_request": False}),
    
    # Complex/edge cases
    ("half day today, full day tomorrow", {"dates": [
        {"date": "2026-01-02", "type": "half_pm", "category": "vacation"},  # assume PM if not specified
        {"date": "2026-01-03", "type": "full", "category": "vacation"},
    ]}),
]
```

---

## Appendix B: Quick Reference Commands

```bash
# Start all services
docker compose up -d

# View logs
docker compose logs -f bot
docker compose logs -f web

# Run migrations
docker compose exec bot alembic upgrade head

# Create new migration
docker compose exec bot alembic revision --autogenerate -m "description"

# Access database
docker compose exec db psql -U leavebot

# Restart bot after code changes
docker compose restart bot

# Full rebuild
docker compose build --no-cache
docker compose up -d

# Backup database
docker compose exec db pg_dump -U leavebot leavebot > backup.sql
```
