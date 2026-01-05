#!/usr/bin/env python3
"""One-time script to import and map Harvest users to Slack users."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import func, select

from leave_bot.database import get_session
from leave_bot.models.user import User
from leave_bot.services.harvest import HarvestService
from leave_bot.utils.logging import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)


async def import_harvest_users() -> None:
    """Import Harvest users and map them to existing Slack users by email."""
    service = HarvestService()

    matched = 0
    unmatched = 0
    already_mapped = 0

    logger.info("fetching_harvest_users")

    try:
        harvest_users = await service.get_users()
        logger.info("found_harvest_users", count=len(harvest_users))

        async with get_session() as session:
            for hu in harvest_users:
                harvest_id = hu["id"]
                email = hu.get("email", "").lower()
                first_name = hu.get("first_name", "")
                last_name = hu.get("last_name", "")
                full_name = f"{first_name} {last_name}".strip()

                if not email:
                    logger.warning("harvest_user_no_email", harvest_id=harvest_id, name=full_name)
                    unmatched += 1
                    continue

                # Find matching user by email
                result = await session.execute(select(User).where(func.lower(User.email) == email))
                user = result.scalar_one_or_none()

                if user:
                    if user.harvest_user_id == harvest_id:
                        already_mapped += 1
                        logger.debug("already_mapped", email=email, harvest_id=harvest_id)
                    else:
                        user.harvest_user_id = harvest_id
                        matched += 1
                        logger.info(
                            "mapped_user",
                            email=email,
                            slack_name=user.slack_display_name,
                            harvest_id=harvest_id,
                            harvest_name=full_name,
                        )
                else:
                    unmatched += 1
                    logger.warning(
                        "no_matching_slack_user",
                        email=email,
                        harvest_id=harvest_id,
                        harvest_name=full_name,
                    )

            await session.commit()

    except Exception as e:
        logger.error("import_failed", error=str(e))
        raise

    logger.info(
        "import_complete",
        matched=matched,
        already_mapped=already_mapped,
        unmatched=unmatched,
    )

    if unmatched > 0:
        logger.warning(
            "some_users_not_matched",
            message="Some Harvest users could not be matched. "
            "Ensure Slack users have matching email addresses.",
        )


if __name__ == "__main__":
    asyncio.run(import_harvest_users())
