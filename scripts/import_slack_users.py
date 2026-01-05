#!/usr/bin/env python3
"""One-time script to import users from Slack workspace."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from slack_sdk.web.async_client import AsyncWebClient
from sqlalchemy import select

from leave_bot.config import get_settings
from leave_bot.database import get_session
from leave_bot.models.user import User
from leave_bot.utils.logging import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)


async def import_slack_users() -> None:
    """Import all users from Slack workspace."""
    settings = get_settings()
    client = AsyncWebClient(token=settings.slack_bot_token)

    imported = 0
    updated = 0
    skipped = 0

    logger.info("fetching_slack_users")

    try:
        response = await client.users_list()
        members = response.get("members", [])
        logger.info("found_slack_users", count=len(members))

        async with get_session() as session:
            for member in members:
                # Skip bots and deactivated users
                if member.get("is_bot") or member.get("deleted"):
                    skipped += 1
                    continue

                slack_user_id = member["id"]
                profile = member.get("profile", {})
                display_name = (
                    profile.get("display_name")
                    or profile.get("real_name")
                    or member.get("name", "Unknown")
                )
                email = profile.get("email")
                timezone = member.get("tz", "Asia/Kolkata")

                # Check if user exists
                result = await session.execute(
                    select(User).where(User.slack_user_id == slack_user_id)
                )
                existing = result.scalar_one_or_none()

                if existing:
                    # Update existing user
                    existing.slack_display_name = display_name
                    existing.email = email
                    existing.slack_timezone = timezone
                    updated += 1
                    logger.debug("updated_user", slack_user_id=slack_user_id, name=display_name)
                else:
                    # Create new user
                    user = User(
                        slack_user_id=slack_user_id,
                        slack_display_name=display_name,
                        email=email,
                        slack_timezone=timezone,
                    )
                    session.add(user)
                    imported += 1
                    logger.debug("imported_user", slack_user_id=slack_user_id, name=display_name)

            await session.commit()

    except Exception as e:
        logger.error("import_failed", error=str(e))
        raise

    logger.info(
        "import_complete",
        imported=imported,
        updated=updated,
        skipped=skipped,
    )


if __name__ == "__main__":
    asyncio.run(import_slack_users())
