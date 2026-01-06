# Configuration

All environment variables and runtime configuration options.

## Environment Variables

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection URL | `postgresql://user:pass@localhost/leavebot` |
| `SLACK_BOT_TOKEN` | Slack Bot OAuth token | `xoxb-123456-abcdef` |
| `SLACK_APP_TOKEN` | Slack App-level token (Socket Mode) | `xapp-1-A01234-567890` |
| `SLACK_SIGNING_SECRET` | Slack signing secret | `abc123def456` |
| `SLACK_CHANNEL_ID` | Channel ID for #wfh-leaves-ooo | `C0XXXXXXX` |
| `OPENAI_API_KEY` | OpenAI API key | `sk-openai-your-key` |
| `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64` | Base64 encoded service account JSON | `eyJhbGciOiJSUzI1NiIs...` |
| `GOOGLE_CALENDAR_ID` | Calendar ID to sync leaves | `leave@group.calendar.google.com` |
| `HARVEST_ACCESS_TOKEN` | Harvest Personal Access Token | `your-harvest-token` |
| `HARVEST_ACCOUNT_ID` | Harvest Account ID | `123456` |
| `HARVEST_PROJECT_ID` | Project ID for leave entries | `12345678` |
| `HARVEST_VACATION_TASK_ID` | Task ID for vacation leave | `87654321` |
| `HARVEST_SICK_TASK_ID` | Task ID for sick leave | `87654322` |

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_MODEL` | OpenAI model for parsing | (required) |
| `TRIGGER_KEYWORDS` | Comma-separated keywords | `leave,ooo,wfh,sick,vacation,pto,day off` |
| `DEFAULT_TIMEZONE` | Fallback timezone | `Asia/Kolkata` |
| `PENDING_ACTION_EXPIRY_MINUTES` | Confirmation timeout | `60` |
| `DEBUG` | Enable debug logging | `false` |

## Settings Class

Location: `leave_bot/config.py`

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database
    database_url: str
    
    # Slack
    slack_bot_token: str
    slack_app_token: str
    slack_signing_secret: str
    slack_channel_id: str
    
    # OpenAI
    openai_api_key: str
    openai_model: str  # Required, no default
    
    # Google Calendar
    google_service_account_json_base64: str
    google_calendar_id: str
    
    # Harvest
    harvest_access_token: str
    harvest_account_id: str
    harvest_project_id: int
    harvest_vacation_task_id: int
    harvest_sick_task_id: int
    
    # Bot settings
    trigger_keywords: str = "leave,ooo,wfh,sick,vacation,pto,day off"
    default_timezone: str = "Asia/Kolkata"
    pending_action_expiry_minutes: int = 60
    
    # Debug
    debug: bool = False
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
```

## Configuration Sources

Priority (highest to lowest):
1. Environment variables
2. `.env` file
3. Default values in Settings class
4. Database `configuration` table (runtime overrides)

## .env.example

```bash
# Database
DATABASE_URL=postgresql://leavebot:password@localhost:5432/leavebot

# Slack
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
SLACK_SIGNING_SECRET=your-signing-secret
SLACK_CHANNEL_ID=C0XXXXXXX

# OpenAI
OPENAI_API_KEY=sk-openai-your-key
OPENAI_MODEL=your-model-here

# Google Calendar (base64 encoded JSON)
GOOGLE_SERVICE_ACCOUNT_JSON_BASE64=eyJhbGciOiJSUzI1NiIs...
GOOGLE_CALENDAR_ID=leave@group.calendar.google.com

# Harvest
HARVEST_ACCESS_TOKEN=your-harvest-token
HARVEST_ACCOUNT_ID=123456
HARVEST_PROJECT_ID=12345678
HARVEST_VACATION_TASK_ID=87654321
HARVEST_SICK_TASK_ID=87654322

# Optional
TRIGGER_KEYWORDS=leave,ooo,wfh,sick,vacation,pto,day off
DEFAULT_TIMEZONE=Asia/Kolkata
PENDING_ACTION_EXPIRY_MINUTES=60
DEBUG=false
```

## Slack Configuration

### Getting Slack Tokens

1. **Bot Token (`SLACK_BOT_TOKEN`)**
   - Go to [Slack API Apps](https://api.slack.com/apps)
   - Select your app → OAuth & Permissions
   - Copy "Bot User OAuth Token" (starts with `xoxb-`)

2. **App Token (`SLACK_APP_TOKEN`)**
   - Your app settings → Basic Information
   - Scroll to "App-Level Tokens"
   - Create token with `connections:write` scope
   - Starts with `xapp-`

3. **Signing Secret (`SLACK_SIGNING_SECRET`)**
   - Your app settings → Basic Information
   - Under "App Credentials"

4. **Channel ID (`SLACK_CHANNEL_ID`)**
   - Right-click channel name in Slack
   - "Copy link"
   - Extract ID from URL: `https://workspace.slack.com/archives/C0XXXXXXX`

### Required Scopes

```
channels:history
channels:read
chat:write
users:read
users:read.email
reactions:write (optional)
```

## Google Calendar Configuration

### Creating Service Account JSON

```bash
# 1. Download JSON from Google Cloud Console
# 2. Base64 encode it
base64 -i service-account.json

# 3. Add to .env (single line, no newlines)
GOOGLE_SERVICE_ACCOUNT_JSON_BASE64=eyJ0eXBlIjoic2VydmljZV9hY2NvdW50Ii...
```

### Finding Calendar ID

- Google Calendar → Settings → Calendar settings
- Under "Integrate calendar"
- Copy "Calendar ID"

For a specific calendar (not primary), it looks like:
```
abcdefg123@group.calendar.google.com
```

## Harvest Configuration

### Getting Harvest Credentials

1. **Access Token**
   - Go to [Harvest Developers](https://id.getharvest.com/developers)
   - Create Personal Access Token

2. **Account ID**
   - Shown in developer portal
   - Or from URL: `https://ACCOUNT_ID.harvestapp.com`

3. **Project and Task IDs**
   - Use Harvest API or inspect network requests
   - Or use admin scripts to list projects/tasks

### Finding Task IDs

```bash
# List projects
curl -H "Authorization: Bearer $HARVEST_ACCESS_TOKEN" \
     -H "Harvest-Account-Id: $HARVEST_ACCOUNT_ID" \
     "https://api.harvestapp.com/v2/projects"

# List tasks for a project
curl -H "Authorization: Bearer $HARVEST_ACCESS_TOKEN" \
     -H "Harvest-Account-Id: $HARVEST_ACCOUNT_ID" \
     "https://api.harvestapp.com/v2/projects/$PROJECT_ID/task_assignments"
```

## Runtime Configuration

The `configuration` table in the database can override some settings at runtime:

| Key | Description |
|-----|-------------|
| `slack_channel_id` | Leave channel ID |
| `trigger_keywords` | Keywords as JSON array |
| `default_timezone` | Default timezone |
| `confirmation_timeout_minutes` | Action expiry time |

### Accessing Runtime Config

Via API:
```bash
# Get all config
GET /api/config

# Update config
PUT /api/config/trigger_keywords
{"value": ["leave", "ooo", "sick"]}
```

Via Code:
```python
from leave_bot.models.configuration import Configuration

async def get_config_value(session, key: str):
    result = await session.execute(
        select(Configuration).where(Configuration.key == key)
    )
    config = result.scalar_one_or_none()
    return config.value if config else None
```

## Fixed Constants

Some values are not configurable in v1:

| Constant | Value | Location |
|----------|-------|----------|
| Half-day AM start | 11:00 | `leave_bot/utils/dates.py` |
| Half-day AM end | 15:00 | `leave_bot/utils/dates.py` |
| Half-day PM start | 15:00 | `leave_bot/utils/dates.py` |
| Half-day PM end | 19:00 | `leave_bot/utils/dates.py` |
| Full day hours | 8.0 | `leave_bot/services/harvest.py` |
| Half day hours | 4.0 | `leave_bot/services/harvest.py` |
| Worker poll interval | 5 seconds | `leave_bot/bot/worker.py` |
| Expiry check interval | 60 seconds | `leave_bot/bot/worker.py` |

## Validation

Settings are validated at startup using Pydantic:

```python
from leave_bot.config import Settings

# Will raise ValidationError if required vars missing
settings = Settings()
```

Common validation errors:
```
pydantic.error_wrappers.ValidationError:
  database_url
    field required (type=value_error.missing)
```

## Docker Environment

In Docker Compose, environment variables are passed to containers:

```yaml
services:
  bot:
    environment:
      DATABASE_URL: postgresql://leavebot:${DB_PASSWORD}@db:5432/leavebot
      SLACK_BOT_TOKEN: ${SLACK_BOT_TOKEN}
      # ... etc
```

Use a `.env` file at the project root for Docker Compose variable substitution.

## Related Documentation

- [Deployment](deployment.md) - Production configuration
- [Integrations](integrations.md) - Service-specific setup
- [Slack Bot](slack-bot.md) - Slack app configuration
