"""Application configuration using Pydantic Settings."""

import base64
import json
from functools import lru_cache
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://leavebot:leavebot@localhost:5432/leavebot",
        description="PostgreSQL connection URL",
    )

    # Slack
    slack_bot_token: str = Field(..., description="Slack Bot OAuth token (xoxb-...)")
    slack_app_token: str = Field(
        ..., description="Slack App-level token for Socket Mode (xapp-...)"
    )
    slack_signing_secret: str = Field(..., description="Slack signing secret")
    slack_channel_id: str = Field(..., description="Channel ID for #wfh-leaves-ooo")

    # OpenAI
    openai_api_key: str = Field(..., description="OpenAI API key")
    openai_model: str = Field(description="OpenAI model to use")

    # Google Calendar
    google_service_account_json_base64: str = Field(
        ..., description="Base64 encoded Google service account JSON"
    )
    google_calendar_id: str = Field(..., description="Google Calendar ID to sync leaves to")

    # Harvest
    harvest_access_token: str = Field(..., description="Harvest Personal Access Token")
    harvest_account_id: str = Field(..., description="Harvest Account ID")
    harvest_project_id: int = Field(..., description="Harvest Project ID for leave entries")
    harvest_vacation_task_id: int = Field(..., description="Harvest Task ID for vacation leave")
    harvest_sick_task_id: int = Field(..., description="Harvest Task ID for sick leave")

    # Bot Configuration
    trigger_keywords: str = Field(
        default="leave,ooo,wfh,sick,vacation,pto,day off",
        description="Comma-separated keywords that trigger leave parsing",
    )
    default_timezone: str = Field(
        default="Asia/Kolkata",
        description="Default timezone for date parsing",
    )

    # Web Admin
    web_host: str = Field(default="0.0.0.0", description="Web server host")
    web_port: int = Field(default=8000, description="Web server port")

    # Pending action expiry
    pending_action_expiry_minutes: int = Field(
        default=60,
        description="Minutes until pending actions expire",
    )

    @property
    def trigger_keywords_list(self) -> list[str]:
        return [kw.strip().lower() for kw in self.trigger_keywords.split(",") if kw.strip()]

    @property
    def google_service_account_info(self) -> dict[str, Any]:
        """Decode and parse Google service account JSON."""
        decoded = base64.b64decode(self.google_service_account_json_base64)
        return json.loads(decoded)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
