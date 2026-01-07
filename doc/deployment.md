# Deployment

Docker configuration, local development setup, and production deployment.

## Local Development

### Prerequisites

- Python 3.12+
- PostgreSQL 16+
- uv package manager

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/nilenso/leavebot.git
   cd leavebot
   ```

2. **Install dependencies**
   ```bash
   uv sync
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

4. **Start PostgreSQL**
   ```bash
   # Using Docker
   docker run -d \
     --name leavebot-db \
     -e POSTGRES_USER=leavebot \
     -e POSTGRES_PASSWORD=devpassword \
     -e POSTGRES_DB=leavebot \
     -p 5432:5432 \
     postgres:16-alpine
   
   # Update DATABASE_URL in .env
   DATABASE_URL=postgresql://leavebot:devpassword@localhost:5432/leavebot
   ```

5. **Run migrations**
   ```bash
   uv run leave-bot migrate
   ```

6. **Start the bot**
   ```bash
   # All components
   uv run leave-bot all
   
   # Or individual components
   uv run leave-bot bot      # Slack bot only
   uv run leave-bot web      # Web admin only
   uv run leave-bot worker   # Background worker only
   ```

### Development Commands

```bash
# Run tests
uv run pytest

# Run with coverage
uv run pytest --cov=leave_bot

# Format code
uv run ruff format .

# Lint
uv run ruff check .

# Type check
uv run ty check

# Create migration
uv run alembic revision --autogenerate -m "description"
```

## Docker Development

### Docker Compose

```bash
# Start all services
docker compose up -d

# View logs
docker compose logs -f bot

# Run migrations
docker compose exec bot alembic upgrade head

# Stop services
docker compose down
```

### docker-compose.yml

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
    command: python -m leave_bot.main bot
    environment:
      DATABASE_URL: postgresql://leavebot:${DB_PASSWORD}@db:5432/leavebot
      SLACK_BOT_TOKEN: ${SLACK_BOT_TOKEN}
      SLACK_APP_TOKEN: ${SLACK_APP_TOKEN}
      SLACK_SIGNING_SECRET: ${SLACK_SIGNING_SECRET}
      SLACK_CHANNEL_ID: ${SLACK_CHANNEL_ID}
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      GOOGLE_SERVICE_ACCOUNT_JSON_BASE64: ${GOOGLE_SERVICE_ACCOUNT_JSON_BASE64}
      GOOGLE_CALENDAR_ID: ${GOOGLE_CALENDAR_ID}
      HARVEST_ACCESS_TOKEN: ${HARVEST_ACCESS_TOKEN}
      HARVEST_ACCOUNT_ID: ${HARVEST_ACCOUNT_ID}
      HARVEST_PROJECT_ID: ${HARVEST_PROJECT_ID}
      HARVEST_VACATION_TASK_ID: ${HARVEST_VACATION_TASK_ID}
      HARVEST_SICK_TASK_ID: ${HARVEST_SICK_TASK_ID}
    depends_on:
      db:
        condition: service_healthy
    restart: unless-stopped

  web:
    build: .
    command: uvicorn leave_bot.web.app:app --host 0.0.0.0 --port 8000
    environment:
      DATABASE_URL: postgresql://leavebot:${DB_PASSWORD}@db:5432/leavebot
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

### Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

# Copy project files
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy application
COPY leave_bot/ ./leave_bot/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Create non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Default command
CMD ["uv", "run", "leave-bot", "all"]
```

## Production Deployment

### DigitalOcean Setup

1. **Create Droplet**
   - Ubuntu 24.04 LTS
   - Basic: 1 vCPU, 1GB RAM ($6/mo)
   - Enable backups

2. **Initial Server Setup**
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
   ```

3. **Deploy Gateway First**
   ```bash
   # The shared gateway must be running before deploying apps
   # See: https://github.com/nilenso/gateway
   ```

4. **Deploy Application**
   ```bash
   # Switch to deploy user
   su - deploy
   
   # Create app directory
   mkdir -p ~/leave-bot
   cd ~/leave-bot
   
   # Copy production compose file
   curl -fsSL https://raw.githubusercontent.com/nilenso/leavebot/main/docker-compose.prod.yml -o docker-compose.prod.yml
   
   # Configure environment
   cp .env.example .env
   nano .env  # Fill in all values (DB_PASSWORD, LEAVEBOT_DOMAIN, etc.)
   
   # Start services
   docker compose -f docker-compose.prod.yml up -d
   ```

5. **DNS Configuration**
   - Point `leavebot.nilenso.com` A record to droplet IP
   - Gateway handles TLS automatically via Let's Encrypt

### Gateway Service

Production uses a shared gateway service ([github.com/nilenso/gateway](https://github.com/nilenso/gateway)) that:
- Handles TLS termination via Let's Encrypt
- Routes traffic based on Docker labels
- Is shared across all nilenso applications

The gateway must be deployed before any apps. See the gateway repo for setup.

**Note:** Routes are configured in the gateway repo's `Caddyfile`. Leavebot's web service connects to the shared `web` network.

### Updates

```bash
# Pull latest code
cd /home/deploy/leave-bot
git pull

# Rebuild and restart
docker compose build --no-cache
docker compose up -d

# Run any new migrations
docker compose exec bot alembic upgrade head
```

### Rollback

```bash
# Revert to previous version
git checkout <previous-commit>
docker compose build
docker compose up -d
```

## Backup & Restore

### Database Backup

```bash
# Create backup
docker compose exec db pg_dump -U leavebot leavebot > backup_$(date +%Y%m%d).sql

# Automated daily backup (add to crontab)
0 2 * * * cd /home/deploy/leave-bot && docker compose exec -T db pg_dump -U leavebot leavebot > backups/backup_$(date +\%Y\%m\%d).sql
```

### Database Restore

```bash
# Restore from backup
docker compose exec -T db psql -U leavebot leavebot < backup.sql
```

## Monitoring

### Health Checks

```bash
# Check all services
curl https://leavebot.nilenso.com/api/health

# Individual checks
curl https://leavebot.nilenso.com/api/health/slack
curl https://leavebot.nilenso.com/api/health/calendar
curl https://leavebot.nilenso.com/api/health/harvest
```

### Logs

```bash
# All logs
docker compose logs -f

# Specific service
docker compose logs -f bot
docker compose logs -f web

# Last 100 lines
docker compose logs --tail=100 bot
```

### Alerting

Set up alerts for:
- Bot disconnected from Slack
- High sync failure rate
- Database connection issues
- Disk space low

Options:
- DigitalOcean Monitoring
- Uptime Robot for health endpoints
- Sentry for error tracking

## Troubleshooting

### Bot Not Responding

1. Check Slack connection:
   ```bash
   curl https://leavebot.nilenso.com/api/health/slack
   ```

2. Verify channel ID is correct

3. Ensure bot is invited to the channel

4. Check logs:
   ```bash
   docker compose logs bot | grep -i error
   ```

### Sync Failures

1. Check health endpoints:
   ```bash
   curl https://leavebot.nilenso.com/api/health/calendar
   curl https://leavebot.nilenso.com/api/health/harvest
   ```

2. Review leave record error messages:
   ```bash
   curl https://leavebot.nilenso.com/api/leaves?status=failed
   ```

3. Retry failed syncs:
   ```bash
   curl -X POST https://leavebot.nilenso.com/api/leaves/42/retry
   ```

### Calendar Events Not Appearing

1. Verify service account has calendar access
2. Check calendar ID is correct
3. Ensure domain-wide delegation if needed

### Database Issues

```bash
# Check database connection
docker compose exec bot python -c "from leave_bot.database import engine; print('OK')"

# Check for lock issues
docker compose exec db psql -U leavebot -c "SELECT * FROM pg_locks;"

# Restart database
docker compose restart db
```

## Quick Reference Commands

```bash
# Start all services
docker compose up -d

# View logs
docker compose logs -f bot

# Run migrations
docker compose exec bot alembic upgrade head

# Create new migration
docker compose exec bot alembic revision --autogenerate -m "description"

# Access database
docker compose exec db psql -U leavebot

# Restart bot
docker compose restart bot

# Full rebuild
docker compose build --no-cache
docker compose up -d

# Backup database
docker compose exec db pg_dump -U leavebot leavebot > backup.sql

# Check disk usage
docker system df
```

## Related Documentation

- [CI/CD](cicd.md) - Automated testing and deployment
- [Configuration](configuration.md) - Environment variables
- [Architecture](architecture.md) - System components
- [Web Admin](web-admin.md) - API endpoints
