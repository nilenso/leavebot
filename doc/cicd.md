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

Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Description |
|--------|-------------|
| `SSH_HOST` | Production server IP or hostname |
| `SSH_USER` | SSH username (e.g., `deploy`) |
| `SSH_PRIVATE_KEY` | SSH private key for authentication |
| `GHCR_PAT` | GitHub PAT with `read:packages` scope (only if repo is private) |

#### Environment Setup

Create a **production** environment at **Settings → Environments → New environment**:
- Name: `production`
- (Optional) Add required reviewers for manual approval
- (Optional) Add environment-specific secrets

### 2. Server Setup

On the production server:

```bash
# Ensure gateway is deployed first (creates the `web` network)
# See: https://github.com/nilenso/gateway

# Create deployment directory
mkdir -p ~/leave-bot
cd ~/leave-bot

# Copy required files from repo
# - docker-compose.prod.yml
# - .env (with production values)

# If repo is private, authenticate with GHCR
echo "YOUR_GHCR_PAT" | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
```

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
