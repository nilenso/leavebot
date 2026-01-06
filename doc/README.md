# Nilenso Leave Bot Documentation

Comprehensive documentation for the automated leave management system.

## Quick Links

| Document | Description |
|----------|-------------|
| [Architecture](architecture.md) | System components, data flow, tech stack |
| [Slack Bot](slack-bot.md) | Message handling, LLM parsing, confirmation flow |
| [Database](database.md) | Schema, models, relationships, migrations |
| [Integrations](integrations.md) | Google Calendar, Harvest, OpenAI setup |
| [Web Admin](web-admin.md) | API endpoints, admin interface |
| [Configuration](configuration.md) | Environment variables, runtime settings |
| [Deployment](deployment.md) | Docker, local dev, production deployment |
| [Technical Specification](leave-bot-tech-spec.md) | Complete technical spec with edge cases |

## Overview

The Leave Bot monitors the `#wfh-leaves-ooo` Slack channel for leave messages, uses an LLM to parse natural language into structured data, and upon user confirmation, syncs the leave to Google Calendar and Harvest.

### Key Features

- 🤖 **Slack Integration** - Socket Mode connection, real-time message processing
- 🧠 **LLM Parsing** - OpenAI-powered natural language understanding
- 📅 **Google Calendar** - Automatic event creation with spanning support
- ⏱️ **Harvest** - Time entry logging for leave tracking
- ✅ **Confirmation Flow** - Interactive buttons for user approval
- 🖥️ **Web Admin** - FastAPI-based management interface

### User Flow

```
1. User posts: "On leave tomorrow"
           ↓
2. Bot parses message with LLM
           ↓
3. Bot replies with confirmation buttons
           ↓
4. User clicks ✓ Confirm
           ↓
5. Background worker syncs to Calendar + Harvest
           ↓
6. Bot updates message with success status
```

### System Components

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Slack     │────▶│  Leave Bot   │────▶│  PostgreSQL │
│  Channel    │     │   + Worker   │     │   Database  │
└─────────────┘     └──────────────┘     └─────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │  OpenAI  │ │  Google  │ │  Harvest │
        │   API    │ │ Calendar │ │   API    │
        └──────────┘ └──────────┘ └──────────┘
```

## Getting Started

### Prerequisites

- Python 3.12+
- PostgreSQL 16+
- Slack workspace with bot configured
- OpenAI API key
- Google service account with Calendar API access
- Harvest Personal Access Token

### Quick Start

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

See [Deployment](deployment.md) for detailed setup instructions.

## Project Structure

```
leave-bot/
├── leave_bot/
│   ├── bot/           # Slack bot handlers
│   ├── services/      # Calendar, Harvest, sync
│   ├── web/           # FastAPI admin
│   └── models/        # SQLAlchemy models
├── alembic/           # Database migrations
├── scripts/           # Import utilities
├── tests/             # Test suite
└── doc/               # Documentation (you are here)
```

## Support

For issues or questions:
1. Check the [Technical Specification](leave-bot-tech-spec.md) for edge cases
2. Review the [Configuration](configuration.md) for setup issues
3. Check health endpoints at `/api/health` for integration status
