# Integrations

Google Calendar, Harvest, and OpenAI integration details.

## Google Calendar

### Overview

The bot creates calendar events in a shared "Leave" calendar. Events can be:
- **All-day events** for full-day leaves
- **Timed events** for half-day leaves
- **Spanning events** for consecutive full-day leaves

### Setup

1. **Create GCP Project**
   - Go to [Google Cloud Console](https://console.cloud.google.com)
   - Create a new project or select existing

2. **Enable Calendar API**
   - Navigate to "APIs & Services" → "Library"
   - Search for "Google Calendar API"
   - Click "Enable"

3. **Create Service Account**
   - Go to "APIs & Services" → "Credentials"
   - Click "Create Credentials" → "Service Account"
   - Give it a name (e.g., "leave-bot")
   - No need to grant roles (handled via calendar sharing)
   - Create and download JSON key

4. **Share Calendar**
   - Open Google Calendar
   - Find the "Leave" calendar
   - Settings → Share with specific people
   - Add the service account email (from JSON key)
   - Grant "Make changes to events" permission

5. **Configure Bot**
   ```bash
   # Base64 encode the JSON key
   base64 -i service-account.json
   
   # Add to .env
   GOOGLE_SERVICE_ACCOUNT_JSON_BASE64=eyJhbGciOiJSUzI1NiIs...
   GOOGLE_CALENDAR_ID=leave@group.calendar.google.com
   ```

### Service Location

`leave_bot/services/calendar.py`

### Event Types

**Full-day Event:**
```python
event = {
    'summary': f'Leave - {user_name}',
    'description': f'Auto-created by Leave Bot\nSlack message: {message_link}',
    'start': {'date': '2026-01-03'},      # All-day event
    'end': {'date': '2026-01-04'},        # End is exclusive
    'eventType': 'default',
}
```

**Half-day Morning (11:00-15:00):**
```python
event = {
    'summary': f'Leave - {user_name} (AM)',
    'start': {
        'dateTime': '2026-01-03T11:00:00',
        'timeZone': user_timezone
    },
    'end': {
        'dateTime': '2026-01-03T15:00:00',
        'timeZone': user_timezone
    },
}
```

**Half-day Afternoon (15:00-19:00):**
```python
event = {
    'summary': f'Leave - {user_name} (PM)',
    'start': {
        'dateTime': '2026-01-03T15:00:00',
        'timeZone': user_timezone
    },
    'end': {
        'dateTime': '2026-01-03T19:00:00',
        'timeZone': user_timezone
    },
}
```

### Spanning Events

Consecutive full-day leaves are grouped into a single calendar event:

```python
# Input: Leave from Jan 5-7
# Creates single event:
event = {
    'summary': 'Leave - User Name',
    'start': {'date': '2026-01-05'},
    'end': {'date': '2026-01-08'},  # End is exclusive
}
```

**Grouping Logic:**
```python
def group_consecutive_dates(dates: list[date]) -> list[list[date]]:
    """Groups consecutive dates for spanning events.
    
    Example:
    [Jan 5, Jan 6, Jan 7, Jan 10, Jan 11] 
    → [[Jan 5, 6, 7], [Jan 10, 11]]
    """
```

All LeaveRecords in a span share the same `calendar_event_id`.

### Half-Day Time Windows

Fixed constants in `leave_bot/utils/dates.py`:

```python
HALF_AM_START = time(11, 0)   # 11:00 AM
HALF_AM_END = time(15, 0)     # 3:00 PM
HALF_PM_START = time(15, 0)   # 3:00 PM
HALF_PM_END = time(19, 0)     # 7:00 PM
```

Times are in the user's timezone (from Slack profile).

---

## Harvest

### Overview

The bot logs time entries to Harvest for leave tracking. Each leave day creates one time entry.

### Setup

1. **Get Personal Access Token**
   - Go to [Harvest Developers](https://id.getharvest.com/developers)
   - Click "Create New Personal Access Token"
   - Give it a name and save the token

2. **Find Account ID**
   - Available in the developer portal
   - Or from Harvest URL: `https://ACCOUNT_ID.harvestapp.com`

3. **Identify Project & Task IDs**
   ```
   Client: Leaves
   └── Project: Leaves
       ├── Task: Personal leave / vacation  ← vacation category
       └── Task: Sick leaves                ← sick category
   ```
   
   Get IDs from Harvest API or admin interface.

4. **Configure Bot**
   ```bash
   HARVEST_ACCESS_TOKEN=your-harvest-token
   HARVEST_ACCOUNT_ID=123456
   HARVEST_PROJECT_ID=12345678
   HARVEST_VACATION_TASK_ID=87654321
   HARVEST_SICK_TASK_ID=87654322
   ```

### Service Location

`leave_bot/services/harvest.py`

### Time Entry Creation

```python
payload = {
    'user_id': harvest_user_id,       # From users table
    'project_id': LEAVES_PROJECT_ID,
    'task_id': VACATION_TASK_ID if category == "vacation" else SICK_TASK_ID,
    'spent_date': '2026-01-03',       # YYYY-MM-DD
    'hours': 8.0,                     # or 4.0 for half-day
    'notes': 'Leave (auto-logged from Slack)'
}

headers = {
    'Authorization': f'Bearer {ACCESS_TOKEN}',
    'Harvest-Account-Id': str(ACCOUNT_ID),
    'User-Agent': 'NilensoLeaveBot (contact@nilenso.com)',
    'Content-Type': 'application/json'
}

response = requests.post(
    'https://api.harvestapp.com/v2/time_entries',
    json=payload,
    headers=headers
)
```

### Hours Logged

| Leave Type | Hours |
|------------|-------|
| Full day | 8.0 |
| Half AM | 4.0 |
| Half PM | 4.0 |

### Task Selection

| Category | Harvest Task |
|----------|--------------|
| `vacation` | Personal leave / vacation |
| `sick` | Sick leaves |

### Admin Permissions

The Harvest token must have admin permissions to create entries for other users. Regular user tokens can only create entries for themselves.

---

## OpenAI

### Overview

The bot uses OpenAI's API for parsing natural language leave messages into structured data.

### Setup

1. **Get API Key**
   - Go to [OpenAI Platform](https://platform.openai.com)
   - Navigate to API keys
   - Create new secret key

2. **Configure Bot**
   ```bash
   OPENAI_API_KEY=sk-openai-your-key
   OPENAI_MODEL=your-model-here
   ```

### Service Location

`leave_bot/bot/parser.py`

### Model Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `OPENAI_MODEL` | (required) | Model to use for parsing |

### Structured Output

The parser uses OpenAI's structured output feature with a Pydantic schema:

```python
class LeaveDate(BaseModel):
    date: str           # YYYY-MM-DD
    type: Literal["full", "half_am", "half_pm"]
    category: Literal["vacation", "sick"]

class ParsedLeave(BaseModel):
    is_leave_request: bool
    is_cancellation: bool
    confidence: Literal["high", "medium", "low"]
    dates: list[LeaveDate]
    original_text_summary: str
    ambiguity_notes: str
```

### System Prompt Context

The LLM receives:
- User's timezone
- Current date and day of week
- Parsing rules

### Cost Considerations

- Choose a model that supports structured output
- Low volume for a small org's leave messages
- Structured output reduces token usage

---

## Sync Orchestration

### Service Location

`leave_bot/services/sync.py`

### Sync Flow

```python
async def sync_leaves(self, leave_records, user, session) -> list[SyncResult]:
    # 1. Separate full-day from half-day records
    full_day_records = [r for r in leave_records if r.leave_type == LeaveType.full]
    half_day_records = [r for r in leave_records if r.leave_type != LeaveType.full]
    
    # 2. Group consecutive full-day dates
    date_groups = group_consecutive_dates([r.date for r in full_day_records])
    
    # 3. Create spanning calendar events
    for group in date_groups:
        if len(group) > 1:
            calendar_event_id = await self.calendar.create_spanning_event(...)
        else:
            calendar_event_id = await self.calendar.create_event(...)
        
        # All records in group share calendar_event_id
    
    # 4. Create individual half-day events
    for record in half_day_records:
        calendar_event_id = await self.calendar.create_timed_event(...)
    
    # 5. Create Harvest entries (always one per day)
    for record in all_records:
        hours = 8.0 if record.leave_type == LeaveType.full else 4.0
        harvest_entry_id = await self.harvest.create_entry(...)
```

### Error Handling

| Scenario | Behavior |
|----------|----------|
| Calendar fails | Retry 3x with backoff, then mark failed |
| Harvest fails | Same; calendar event preserved |
| Partial success | Mark appropriate status per service |
| Rate limiting | Exponential backoff |

---

## Health Checks

Each integration has a health check endpoint:

| Endpoint | Service |
|----------|---------|
| `/api/health/slack` | Slack connection |
| `/api/health/calendar` | Google Calendar API |
| `/api/health/harvest` | Harvest API |

### Health Check Location

`leave_bot/web/routes/health.py`

```python
@router.get("/health/calendar")
async def health_calendar():
    try:
        # Try to list upcoming events
        await calendar_service.list_events(max_results=1)
        return {"status": "up", "latency_ms": ...}
    except Exception as e:
        return {"status": "down", "error": str(e)}
```

## Related Documentation

- [Configuration](configuration.md) - All environment variables
- [Slack Bot](slack-bot.md) - Slack integration details
- [Architecture](architecture.md) - System overview
