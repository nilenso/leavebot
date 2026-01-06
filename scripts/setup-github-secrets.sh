#!/bin/bash
# Setup GitHub secrets for leavebot deployment from a .env file
#
# Usage: ./scripts/setup-github-secrets.sh [path-to-env-file]
#
# Examples:
#   ./scripts/setup-github-secrets.sh              # Uses .env in current directory
#   ./scripts/setup-github-secrets.sh .env.prod    # Uses specific file

set -e

ENV_FILE="${1:-.env}"

echo "=== LeaveBot GitHub Secrets Setup ==="
echo ""

# Check if gh is installed and authenticated
if ! command -v gh &> /dev/null; then
    echo "Error: GitHub CLI (gh) is not installed."
    echo "Install it from: https://cli.github.com/"
    exit 1
fi

if ! gh auth status &> /dev/null; then
    echo "Error: Not authenticated with GitHub CLI."
    echo "Run: gh auth login"
    exit 1
fi

# Check if .env file exists
if [ ! -f "$ENV_FILE" ]; then
    echo "Error: File not found: $ENV_FILE"
    echo ""
    echo "Usage: $0 [path-to-env-file]"
    echo ""
    echo "Create a .env file from the example:"
    echo "  cp .env.example .env"
    echo "  # Fill in values, then run this script"
    exit 1
fi

echo "Reading secrets from: $ENV_FILE"
echo ""

# Application secrets to read from .env file
APP_SECRETS=(
    "DB_PASSWORD"
    "SLACK_BOT_TOKEN"
    "SLACK_APP_TOKEN"
    "SLACK_SIGNING_SECRET"
    "SLACK_CHANNEL_ID"
    "OPENAI_API_KEY"
    "OPENAI_MODEL"
    "GOOGLE_SERVICE_ACCOUNT_JSON_BASE64"
    "GOOGLE_CALENDAR_ID"
    "HARVEST_ACCESS_TOKEN"
    "HARVEST_ACCOUNT_ID"
    "HARVEST_PROJECT_ID"
    "HARVEST_VACATION_TASK_ID"
    "HARVEST_SICK_TASK_ID"
    "GOOGLE_OAUTH_CLIENT_ID"
    "GOOGLE_OAUTH_CLIENT_SECRET"
    "SESSION_SECRET_KEY"
    "ALLOWED_EMAIL_DOMAIN"
    "OAUTH_REDIRECT_URI"
)

# Function to get value from .env file
get_env_value() {
    local key=$1
    local value
    # Extract value, handling quotes and spaces
    value=$(grep -E "^${key}=" "$ENV_FILE" | head -1 | cut -d'=' -f2-)
    # Remove surrounding quotes if present
    value="${value%\"}"
    value="${value#\"}"
    value="${value%\'}"
    value="${value#\'}"
    echo "$value"
}

# Function to set a secret
set_secret() {
    local name=$1
    local value=$2
    
    if [ -n "$value" ]; then
        echo "$value" | gh secret set "$name"
        echo "✓ $name"
    else
        echo "⚠ $name (empty/missing - skipped)"
    fi
}

echo "=== Deployment Secrets (not in .env) ==="
echo ""
echo "These are required for CI/CD to SSH into your server."
echo ""

# SSH_HOST
read -p "SSH_HOST (server IP or hostname): " ssh_host
if [ -n "$ssh_host" ]; then
    set_secret "SSH_HOST" "$ssh_host"
else
    echo "⚠ SSH_HOST (skipped)"
fi

# SSH_USER
read -p "SSH_USER (e.g., deploy): " ssh_user
if [ -n "$ssh_user" ]; then
    set_secret "SSH_USER" "$ssh_user"
else
    echo "⚠ SSH_USER (skipped)"
fi

# SSH_PRIVATE_KEY
read -p "SSH_PRIVATE_KEY file path (e.g., ~/.ssh/id_ed25519): " ssh_key_path
if [ -n "$ssh_key_path" ] && [ -f "$ssh_key_path" ]; then
    gh secret set SSH_PRIVATE_KEY < "$ssh_key_path"
    echo "✓ SSH_PRIVATE_KEY"
else
    echo "⚠ SSH_PRIVATE_KEY (skipped)"
fi

# GHCR_PAT (optional)
echo ""
read -p "Is this a private repository? (y/N): " is_private
if [[ "$is_private" =~ ^[Yy]$ ]]; then
    read -sp "GHCR_PAT (GitHub PAT with read:packages scope): " ghcr_pat
    echo ""
    if [ -n "$ghcr_pat" ]; then
        set_secret "GHCR_PAT" "$ghcr_pat"
    fi
fi

echo ""
echo "=== Application Secrets (from $ENV_FILE) ==="
echo ""

for secret in "${APP_SECRETS[@]}"; do
    value=$(get_env_value "$secret")
    set_secret "$secret" "$value"
done

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Secrets configured. Verify with:"
echo "  gh secret list"
echo ""
echo "Create the production environment (if not exists):"
echo "  gh api repos/\$(gh repo view --json nameWithOwner -q .nameWithOwner)/environments/production -X PUT"
echo ""
