# CI/CD

Automated testing and deployment using GitHub Actions.

## Overview

The CI/CD pipeline is defined in `.github/workflows/ci.yml` and handles:

1. **CI (on all PRs and pushes to main):**
   - Lint & format checking (ruff)
   - Type checking (ty)
   - Unit tests (pytest)

2. **CD (on push to main only):**
   - Build Docker image
   - Push to GitHub Container Registry (GHCR)
   - Deploy to production server via SSH
   - Run database migrations

## Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     Push to main / PR                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
   ┌─────────┐          ┌──────────┐          ┌─────────┐
   │  Lint   │          │ Typecheck│          │  Test   │
   │ (ruff)  │          │   (ty)   │          │(pytest) │
   └─────────┘          └──────────┘          └─────────┘
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ All CI passed?  │
                    └─────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
         (PR only)                    (main branch only)
              │                               │
              ▼                               ▼
         ┌────────┐                  ┌─────────────────┐
         │  Done  │                  │ Build & Push    │
         └────────┘                  │ Docker Image    │
                                     └─────────────────┘
                                              │
                                              ▼
                                     ┌─────────────────┐
                                     │ Deploy to       │
                                     │ Production      │
                                     └─────────────────┘
```

## Setup

### 1. GitHub Repository Settings

#### Required Secrets

All application secrets are stored in GitHub and deployed to the server during CI/CD.

Run the setup script to add all secrets interactively:

```bash
./scripts/setup-github-secrets.sh
```

Or add them manually via `gh secret set <NAME>`:

**Deployment Secrets:**
| Secret | Description |
|--------|-------------|
| `SSH_HOST` | Production server IP or hostname |
| `SSH_USER` | SSH username (e.g., `deploy`) |
| `SSH_PRIVATE_KEY` | SSH private key for authentication |
| `GHCR_PAT` | GitHub PAT with `read:packages` scope (only if repo is private) |

**Application Secrets:**
| Secret | Description |
|--------|-------------|
| `DB_PASSWORD` | PostgreSQL password |
| `SLACK_BOT_TOKEN` | Slack Bot OAuth token (`xoxb-...`) |
| `SLACK_APP_TOKEN` | Slack App-level token (`xapp-...`) |
| `SLACK_SIGNING_SECRET` | Slack signing secret |
| `SLACK_CHANNEL_ID` | Channel ID for #wfh-leaves-ooo |
| `OPENAI_API_KEY` | OpenAI API key |
| `OPENAI_MODEL` | OpenAI model (e.g., `gpt-4o-mini`) |
| `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64` | Base64 encoded service account JSON |
| `GOOGLE_CALENDAR_ID` | Google Calendar ID for leave events |
| `HARVEST_ACCESS_TOKEN` | Harvest Personal Access Token |
| `HARVEST_ACCOUNT_ID` | Harvest Account ID |
| `HARVEST_PROJECT_ID` | Harvest Project ID for leave entries |
| `HARVEST_VACATION_TASK_ID` | Harvest Task ID for vacation/PTO |
| `HARVEST_SICK_TASK_ID` | Harvest Task ID for sick leave |
| `GOOGLE_OAUTH_CLIENT_ID` | Google OAuth Client ID |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Google OAuth Client Secret |
| `SESSION_SECRET_KEY` | Random secret for session encryption |
| `ALLOWED_EMAIL_DOMAIN` | Email domain allowed to access admin |
| `OAUTH_REDIRECT_URI` | OAuth callback URL |

#### Environment Setup

Create a **production** environment at **Settings → Environments → New environment**:
- Name: `production`
- (Optional) Add required reviewers for manual approval

### 2. Server Setup

On the production server:

```bash
# Ensure gateway is deployed first (creates the `web` network)
# See: https://github.com/nilenso/gateway

# Create deployment directory
mkdir -p ~/leave-bot

# That's it! The CI/CD pipeline will:
# - Generate .env from GitHub secrets
# - Copy docker-compose.prod.yml to the server
# - Pull and run the containers
```

**Note:** The `.env` file is automatically generated and deployed from GitHub secrets during CI/CD. You don't need to manually create or maintain it on the server.

### 3. Gateway Dependency

This app requires the shared gateway service to be running. The gateway:
- Creates the `web` Docker network
- Handles TLS termination
- Routes traffic based on Docker labels

See [gateway repo](https://github.com/nilenso/gateway) for setup.

### 4. Update Image Name (if needed)

Edit `docker-compose.prod.yml` and update the image name to match your GitHub repository:

```yaml
image: ghcr.io/<owner>/<repo>:latest
```

For example:
- `ghcr.io/nilenso/leavebot:latest`
- `ghcr.io/nilenso/nilenso-leave-bot:latest`

## Files

| File | Purpose |
|------|---------|
| `.github/workflows/ci.yml` | CI/CD pipeline definition |
| `docker-compose.yml` | Local development (builds image locally, includes Caddy) |
| `docker-compose.prod.yml` | Production deployment (pulls from GHCR, uses shared gateway) |
| `Dockerfile` | Multi-stage Docker build |

## Gateway Integration

Production uses a shared [gateway service](https://github.com/nilenso/gateway) running Caddy for:
- TLS termination (automatic Let's Encrypt)
- Routing based on static Caddyfile
- Shared across all nilenso apps

Routes are configured in the gateway repo's `Caddyfile`. The web service connects to the shared `web` network.

## Manual Deployment

If you need to deploy manually:

```bash
# On the server
cd ~/leave-bot

# Pull latest image
docker compose -f docker-compose.prod.yml pull

# Restart services
docker compose -f docker-compose.prod.yml up -d

# Run migrations
docker compose -f docker-compose.prod.yml exec -T bot python -m alembic upgrade head
```

## Rollback

To rollback to a previous version:

```bash
# Find the previous image SHA
# Go to GitHub → Packages → Container → leavebot → Versions

# Update docker-compose.prod.yml to use specific SHA
# image: ghcr.io/nilenso/leavebot:abc1234

# Or use the CLI
docker pull ghcr.io/nilenso/leavebot:abc1234
docker compose -f docker-compose.prod.yml up -d
```

## Troubleshooting

### CI Failures

```bash
# Run checks locally
uv run ruff format --check .   # Format check
uv run ruff check .            # Lint
uv run ty check                # Type check
uv run pytest                  # Tests
```

### Deployment Failures

1. **SSH connection failed:**
   - Verify `SSH_HOST`, `SSH_USER`, and `SSH_PRIVATE_KEY` secrets
   - Ensure the SSH key is added to `~/.ssh/authorized_keys` on server

2. **Docker pull failed:**
   - Check if GHCR authentication is set up (for private repos)
   - Verify the image name in `docker-compose.prod.yml` matches the repo

3. **Migration failed:**
   - Check database connectivity
   - Review migration logs: `docker compose -f docker-compose.prod.yml logs bot`

### Viewing Logs

```bash
# On server
docker compose -f docker-compose.prod.yml logs -f bot
docker compose -f docker-compose.prod.yml logs -f web
```

## Related Documentation

- [Deployment](deployment.md) - Server setup and manual deployment
- [Configuration](configuration.md) - Environment variables
