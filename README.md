# Nilenso Leave Bot

A Slack bot that monitors the `#wfh-leaves-ooo` channel for leave messages, uses LLM to parse them, and syncs confirmed leaves to Google Calendar and Harvest.

## Features

- 🤖 **Slack Integration**: Monitors leave channel using Socket Mode
- 🧠 **LLM Parsing**: Uses OpenAI to understand natural language leave requests
- 📅 **Google Calendar Sync**: Creates calendar events for leave days
- ⏱️ **Harvest Integration**: Logs time entries for leave tracking
- 🖥️ **Web Admin**: FastAPI-based admin interface for management
- ✅ **Confirmation Flow**: Interactive buttons for user confirmation

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Slack     │────▶│  Leave Bot   │────▶│  PostgreSQL │
│  Channel    │     │  (FastAPI)   │     │   Database  │
└─────────────┘     └──────────────┘     └─────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │  OpenAI  │ │  Google  │ │  Harvest │
        │   API    │ │ Calendar │ │   API    │
        └──────────┘ └──────────┘ └──────────┘
```

## Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL 16+
- Slack workspace with bot configured
- OpenAI API key
- Google service account with Calendar API access
- Harvest account with Personal Access Token

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/nilenso/leavebot.git
   cd leavebot
   ```

2. Install dependencies:
   ```bash
   uv sync
   ```

3. Copy and configure environment:
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

4. Run database migrations:
   ```bash
   uv run leave-bot migrate
   ```

5. Import users:
   ```bash
   uv run python scripts/import_slack_users.py
   uv run python scripts/import_harvest_users.py
   ```

6. Start the bot:
   ```bash
   uv run leave-bot all
   ```

### Docker Deployment

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f bot

# Stop services
docker-compose down
```

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection URL | Yes |
| `SLACK_BOT_TOKEN` | Slack Bot OAuth token (xoxb-...) | Yes |
| `SLACK_APP_TOKEN` | Slack App-level token (xapp-...) | Yes |
| `SLACK_SIGNING_SECRET` | Slack signing secret | Yes |
| `SLACK_CHANNEL_ID` | Channel ID for #wfh-leaves-ooo | Yes |
| `OPENAI_API_KEY` | OpenAI API key | Yes |
| `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64` | Base64 encoded service account JSON | Yes |
| `GOOGLE_CALENDAR_ID` | Calendar ID to sync leaves | Yes |
| `HARVEST_ACCESS_TOKEN` | Harvest Personal Access Token | Yes |
| `HARVEST_ACCOUNT_ID` | Harvest Account ID | Yes |
| `HARVEST_PROJECT_ID` | Project ID for leave entries | Yes |
| `HARVEST_VACATION_TASK_ID` | Task ID for vacation | Yes |
| `HARVEST_SICK_TASK_ID` | Task ID for sick leave | Yes |

### Slack App Configuration

1. Create a new Slack app at https://api.slack.com/apps
2. Enable Socket Mode
3. Add the following bot token scopes:
   - `channels:history`
   - `channels:read`
   - `chat:write`
   - `users:read`
   - `users:read.email`
4. Subscribe to these events:
   - `message.channels`
5. Install the app to your workspace
6. Invite the bot to `#wfh-leaves-ooo`

### Google Calendar Setup

1. Create a service account in Google Cloud Console
2. Enable the Google Calendar API
3. Download the service account JSON key
4. Base64 encode it: `base64 -i service-account.json`
5. Share the target calendar with the service account email

## Usage

### Posting Leave

Post a message in `#wfh-leaves-ooo`:

```
On leave tomorrow
```

```
Taking sick leave from 5th to 7th January
```

```
Half day tomorrow afternoon
```

The bot will:
1. Parse your message using LLM
2. Send a confirmation message with buttons
3. On confirmation, sync to Calendar and Harvest

### Admin Interface

Access the web admin at `http://localhost:8000`:

- **Dashboard**: Overview and health status
- **Users**: Manage user mappings
- **Leaves**: View and manage leave records
- **Config**: Update configuration

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | System health check |
| `/api/users` | GET/POST | List/create users |
| `/api/users/{id}` | GET/PUT/DELETE | Manage user |
| `/api/users/import/slack` | POST | Import from Slack |
| `/api/users/import/harvest` | POST | Import from Harvest |
| `/api/leaves` | GET | List leave records |
| `/api/leaves/{id}` | GET/DELETE | Manage leave |
| `/api/leaves/{id}/retry` | POST | Retry failed sync |
| `/api/config` | GET | List configuration |
| `/api/config/{key}` | GET/PUT/DELETE | Manage config |

## Development

### Running Tests

```bash
# Install dependencies (includes dev group)
uv sync

# Run tests
uv run pytest

# Run with coverage
uv run pytest --cov=leave_bot
```

### Code Style

```bash
# Format code
uv run ruff format .

# Lint
uv run ruff check .

# Type check
uv run ty check
```

## Troubleshooting

### Bot not responding

1. Check Slack connection: `GET /api/health/slack`
2. Verify channel ID is correct
3. Ensure bot is invited to the channel

### Sync failures

1. Check health endpoints for service status
2. Review leave record error messages
3. Retry failed syncs via admin or API

### Calendar events not appearing

1. Verify service account has calendar access
2. Check calendar ID is correct
3. Ensure domain-wide delegation if using user calendars

## License

MIT License - see LICENSE file for details.
