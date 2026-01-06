# Slack Bot

Slack bot behavior, message parsing, confirmation flow, and button handlers.

## Overview

The bot uses Slack's Socket Mode for real-time communication without needing a public URL. It monitors a specific channel for leave-related messages and processes them through an LLM-powered parser.

## Slack App Configuration

### Required Bot Token Scopes

| Scope | Purpose |
|-------|---------|
| `channels:history` | Read messages in public channels |
| `channels:read` | View basic channel info |
| `chat:write` | Send messages and replies |
| `users:read` | Get user info (display names) |
| `users:read.email` | Get user email for matching |
| `reactions:write` | Add reactions (optional) |

### Event Subscriptions

Subscribe to:
- `message.channels` - Messages in public channels

### Socket Mode

- Enable Socket Mode in app settings
- Generate App-Level Token with `connections:write` scope
- No public URL required

### Installation Steps

1. Create a new Slack app at https://api.slack.com/apps
2. Enable Socket Mode under "Socket Mode"
3. Add bot token scopes under "OAuth & Permissions"
4. Subscribe to events under "Event Subscriptions"
5. Install the app to your workspace
6. Invite the bot to `#wfh-leaves-ooo`

## Message Handling

### Handler Location

`leave_bot/bot/handlers.py`

### Message Filter Logic

```python
def should_process_message(message, channel_id, trigger_keywords):
    # 1. Must be in the configured leave channel
    if message["channel"] != channel_id:
        return False
    
    # 2. Ignore bot messages
    if message.get("bot_id"):
        return False
    
    # 3. Must contain a trigger keyword
    text = message.get("text", "").lower()
    keywords = trigger_keywords.split(",")
    return any(keyword.strip() in text for keyword in keywords)
```

### Default Trigger Keywords

```
leave, ooo, wfh, sick, vacation, pto, day off
```

### Thread Handling

- **Top-level messages**: Primary trigger point, require trigger keywords
- **Thread replies**: Processed without keyword check (thread context is the signal)
- **After confirmation**: Bot stops listening to the thread once a leave is confirmed/completed
- **Superseding**: New confirmations in a thread expire and update previous pending confirmations

## LLM Parsing

### Parser Location

`leave_bot/bot/parser.py`

### System Prompt

The LLM receives context about:
- User's timezone (from Slack profile)
- Current date and day of week
- Parsing rules for dates, leave types, categories

### Output Schema (Pydantic)

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

### Parsing Rules

| Rule | Behavior |
|------|----------|
| Relative dates | "tomorrow", "next Monday" → absolute dates |
| Date ranges | "5th to 10th" → 6 individual date entries |
| Half days | "first half", "afternoon" → `half_am` or `half_pm` |
| Sick vs vacation | Keywords like "fever", "unwell" → `sick` |
| WFH messages | Return `is_leave_request: false` |
| Policy questions | Return `is_leave_request: false` |

### Confidence Handling

| Level | Action |
|-------|--------|
| `high` | Proceed with confirmation |
| `medium` | Include ambiguity note in confirmation |
| `low` | Ask for clarification instead |

### Date Validation

- Reject dates before Jan 1 of current year
- Past dates within current year are allowed (retroactive logging)
- Future dates in following months are accepted

### Example Parses

```python
# Input: "on leave tomorrow"
{
    "is_leave_request": True,
    "dates": [{"date": "2026-01-07", "type": "full", "category": "vacation"}],
    "confidence": "high"
}

# Input: "down with fever, taking today off"
{
    "is_leave_request": True,
    "dates": [{"date": "2026-01-06", "type": "full", "category": "sick"}],
    "confidence": "high"
}

# Input: "half day tomorrow afternoon"
{
    "is_leave_request": True,
    "dates": [{"date": "2026-01-07", "type": "half_pm", "category": "vacation"}],
    "confidence": "high"
}

# Input: "can someone explain leave policy?"
{
    "is_leave_request": False,
    "dates": [],
    "confidence": "high"
}
```

## Confirmation Flow

### Block Kit Message

Location: `leave_bot/bot/blocks.py`

### Standard Confirmation

```
┌────────────────────────────────────────────────────────────┐
│ 📅 I'll record the following leave for you:                │
│                                                            │
│ • Friday, Jan 3, 2026 — Full day (Vacation)               │
│ • Monday, Jan 6, 2026 — Full day (Vacation)               │
│                                                            │
│ This will:                                                 │
│ • Create events in the Leave calendar                      │
│ • Log 8 hours per full day in Harvest                     │
│                                                            │
│ ┌─────────────┐  ┌─────────────┐                          │
│ │ ✓ Confirm   │  │ ✗ Cancel    │                          │
│ └─────────────┘  └─────────────┘                          │
└────────────────────────────────────────────────────────────┘
```

### With Conflict Warning

```
┌────────────────────────────────────────────────────────────┐
│ ⚠️ You already have leave recorded for Jan 3, 2026.        │
│                                                            │
│ I'll record the following NEW leave:                       │
│ • Monday, Jan 6, 2026 — Full day (Vacation)               │
│                                                            │
│ ┌─────────────┐  ┌─────────────┐                          │
│ │ ✓ Confirm   │  │ ✗ Cancel    │                          │
│ └─────────────┘  └─────────────┘                          │
└────────────────────────────────────────────────────────────┘
```

### Success Message

After sync completes:
```
┌────────────────────────────────────────────────────────────┐
│ ✅ Leave recorded successfully!                            │
│                                                            │
│ • Friday, Jan 3, 2026 — Full day (Vacation)               │
│                                                            │
│ ✓ Calendar event created                                  │
│ ✓ Harvest time entry logged                               │
└────────────────────────────────────────────────────────────┘
```

### Error Message

If sync fails:
```
┌────────────────────────────────────────────────────────────┐
│ ⚠️ Leave recorded with issues:                             │
│                                                            │
│ • Friday, Jan 3, 2026 — Full day (Vacation)               │
│                                                            │
│ ✓ Calendar event created                                  │
│ ✗ Harvest sync failed: Rate limit exceeded                │
│                                                            │
│ The admin can retry the Harvest sync later.               │
└────────────────────────────────────────────────────────────┘
```

## Button Handlers

### Action IDs

| Action ID | Purpose |
|-----------|---------|
| `leave_confirm` | User confirms the leave request |
| `leave_cancel` | User cancels the request |

### Handler Logic

```python
@app.action("leave_confirm")
async def handle_leave_confirm(ack, body, client):
    # 1. Acknowledge immediately (Slack 3-second requirement)
    await ack()
    
    # 2. Extract pending action ID from button value
    action_id = body["actions"][0]["value"]
    
    # 3. Mark pending action as confirmed
    # Worker will pick it up for processing
    
    # 4. Update message to show "Processing..."
```

```python
@app.action("leave_cancel")
async def handle_leave_cancel(ack, body, client):
    # 1. Acknowledge immediately
    await ack()
    
    # 2. Mark pending action as cancelled
    
    # 3. Update message to show "Cancelled"
```

### Idempotency

- Double-clicks are handled gracefully
- Second click shows "already processed" message
- PendingAction status is checked before processing

## Cancellation Handling

### Detection

When LLM detects `is_cancellation: true`:

1. **With specific dates mentioned**:
   - Look up those dates in leave_records
   - Offer to delete calendar events and Harvest entries

2. **Without specific dates**:
   - Reply asking for clarification

### Clarification Prompt

```
┌────────────────────────────────────────────────────────────┐
│ 🔄 Which leave dates would you like to cancel?             │
│                                                            │
│ Please reply in this thread with the specific dates,      │
│ e.g., "cancel my leave on Jan 3" or "cancel Jan 3-5"       │
└────────────────────────────────────────────────────────────┘
```

### Cancellation Confirmation

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

## Background Worker

### Worker Location

`leave_bot/bot/worker.py`

### Processing Loop

```python
class Worker:
    POLL_INTERVAL_SECONDS = 5
    EXPIRE_CHECK_INTERVAL_SECONDS = 60
    
    async def run(self):
        while self.running:
            await self.process_confirmed_actions()
            await self.expire_old_actions()
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
```

### Confirmed Action Processing

1. Fetch `pending_actions` with `status='confirmed'`
2. Mark as `'processing'`
3. Create `leave_records` entries
4. Call sync service (Calendar + Harvest)
5. Mark as `'completed'`
6. Update Slack message with results

### Expiry Handling

- Pending actions expire after 1 hour (configurable)
- Worker marks expired actions and disables buttons
- User must post a new message to try again

### No Automatic Retries

The worker does **not** automatically retry failed syncs. This is intentional:
- The database is not the source of truth—Slack confirmations are
- Users may delete leaves externally (in Calendar/Harvest)
- Automatic retries would recreate deleted entries

Failed syncs can be manually retried via the web admin API (`POST /api/leaves/{id}/retry`).

## Superseding Confirmations

When a user posts a follow-up message in a thread that triggers a new confirmation:

1. All previous `pending` actions in that thread are marked `expired`
2. Their Slack messages are updated to show "↩️ This request was superseded by a newer one below"
3. Only the newest confirmation has active buttons

This ensures users only have one active confirmation to deal with at a time.

## Thread Completion

Once a leave is confirmed in a thread:

1. The `PendingAction` status becomes `confirmed` → `processing` → `completed`
2. The bot stops listening to further messages in that thread
3. Users wanting to modify the leave must use a new top-level message or the web admin

## Deduplication

### Event ID Strategy

- Slack Events API provides unique `event_id`
- Stored in `pending_actions.slack_event_id`
- Unique index prevents duplicate processing
- Insert conflict → treat as retry, no-op

## Edge Cases

| Scenario | Handling |
|----------|----------|
| Message edits | Ignored; user must cancel and re-post |
| User deletes message | Pending action expires naturally |
| Bot message deleted | Pending action expires naturally |
| Weekend dates | Optional warning in confirmation |
| @mentions in message | Stripped before parsing |

## Related Documentation

- [Architecture](architecture.md) - System overview
- [Database](database.md) - PendingAction and LeaveRecord models
- [Integrations](integrations.md) - OpenAI configuration
- [Configuration](configuration.md) - Slack environment variables
