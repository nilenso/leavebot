# Nilenso Leave Bot

A Slack bot that monitors the `#wfh-leaves-ooo` channel for leave messages, uses LLM to parse them, and syncs confirmed leaves to Google Calendar and Harvest.

## Features

- 🤖 **Slack Integration** - Monitors leave channel using Socket Mode
- 🧠 **LLM Parsing** - Uses OpenAI to understand natural language leave requests
- 📅 **Google Calendar Sync** - Creates calendar events (with spanning support)
- ⏱️ **Harvest Integration** - Logs time entries for leave tracking
- ✅ **Confirmation Flow** - Interactive buttons for user approval
- 🖥️ **Web Admin** - FastAPI-based management interface

## Quick Start

```bash
# Install dependencies
uv sync

# Configure environment
cp .env.example .env
# Edit .env with your credentials

# Run migrations
uv run leave-bot migrate

# Start everything
uv run leave-bot all
```

## Documentation

See the **[doc/](doc/)** folder for comprehensive documentation:

| Document | Description |
|----------|-------------|
| [Overview](doc/README.md) | Documentation index and quick navigation |
| [Architecture](doc/architecture.md) | System components, data flow, tech stack |
| [Slack Bot](doc/slack-bot.md) | Message handling, LLM parsing, button handlers |
| [Database](doc/database.md) | Schema, models, relationships, migrations |
| [Integrations](doc/integrations.md) | Google Calendar, Harvest, OpenAI setup |
| [Web Admin](doc/web-admin.md) | API endpoints, admin interface |
| [Configuration](doc/configuration.md) | Environment variables, runtime settings |
| [Deployment](doc/deployment.md) | Docker, local dev, production deployment |
| [Tech Spec](doc/leave-bot-tech-spec.md) | Complete technical specification |

## Usage

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

The bot will parse your message, send a confirmation prompt, and upon approval, sync to Calendar and Harvest.

## Development

```bash
# Run tests
uv run pytest

# Format code
uv run ruff format .

# Lint
uv run ruff check .
```

## License

MIT License - see LICENSE file for details.
