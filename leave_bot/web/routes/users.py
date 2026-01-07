"""User management endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from leave_bot.config import get_settings
from leave_bot.database import get_db
from leave_bot.models.user import User
from leave_bot.services.harvest import HarvestService
from leave_bot.utils.logging import get_logger
from leave_bot.web.schemas import (
    ImportResult,
    PaginatedResponse,
    UserCreate,
    UserResponse,
    UserUpdate,
)

router = APIRouter()
logger = get_logger(__name__)


@router.get("/users", response_model=PaginatedResponse[UserResponse])
async def list_users(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    search: str | None = None,
    active_only: bool = True,
    session: AsyncSession = Depends(get_db),
) -> PaginatedResponse[UserResponse]:
    """List users with pagination and search."""
    # Build base query
    query = select(User)
    count_query = select(func.count()).select_from(User)

    # Apply filters
    if active_only:
        query = query.where(User.is_active.is_(True))
        count_query = count_query.where(User.is_active.is_(True))

    if search:
        search_filter = User.slack_display_name.ilike(f"%{search}%") | User.email.ilike(
            f"%{search}%"
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    # Get total count
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.order_by(User.slack_display_name).offset(offset).limit(page_size)

    # Execute query
    result = await session.execute(query)
    users = result.scalars().all()

    return PaginatedResponse(
        items=[UserResponse.model_validate(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.post("/users", response_model=UserResponse, status_code=201)
async def create_user(
    user_data: UserCreate,
    session: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Create a new user."""
    # Check if user already exists
    existing = await session.execute(
        select(User).where(User.slack_user_id == user_data.slack_user_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"User with Slack ID {user_data.slack_user_id} already exists",
        )

    user = User(**user_data.model_dump())
    session.add(user)
    await session.commit()
    await session.refresh(user)

    logger.info("user_created", user_id=user.id, slack_user_id=user.slack_user_id)
    return UserResponse.model_validate(user)


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    session: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Get a user by ID."""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserResponse.model_validate(user)


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    session: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Update a user."""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Update only provided fields
    update_data = user_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    await session.commit()
    await session.refresh(user)

    logger.info("user_updated", user_id=user.id)
    return UserResponse.model_validate(user)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    session: AsyncSession = Depends(get_db),
) -> None:
    """Soft delete a user (set inactive)."""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = False
    await session.commit()

    logger.info("user_deleted", user_id=user.id)


@router.post("/users/import/slack", response_model=ImportResult)
async def import_slack_users(
    session: AsyncSession = Depends(get_db),
) -> ImportResult:
    """Import users from the configured Slack leave channel."""
    from slack_sdk.errors import SlackApiError
    from slack_sdk.web.async_client import AsyncWebClient

    settings = get_settings()
    client = AsyncWebClient(token=settings.slack_bot_token)

    imported = 0
    updated = 0
    skipped = 0
    errors: list[str] = []

    try:
        # First, get channel members from the configured leave channel
        channel_id = settings.slack_channel_id
        channel_member_ids: list[str] = []

        try:
            # Paginate through all channel members
            cursor = None
            while True:
                response = await client.conversations_members(
                    channel=channel_id,
                    cursor=cursor,
                    limit=200,
                )
                channel_member_ids.extend(response.get("members", []))

                # Check for pagination
                cursor = response.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break

        except SlackApiError as e:
            error_code = e.response.get("error", "unknown_error")
            if error_code == "channel_not_found":
                raise HTTPException(
                    status_code=404,
                    detail=f"Channel {channel_id} not found. Verify the channel ID is correct.",
                )
            elif error_code == "not_in_channel":
                raise HTTPException(
                    status_code=403,
                    detail=f"Bot is not a member of channel {channel_id}. Please add the bot to the channel first.",
                )
            else:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to fetch channel members: {error_code}",
                )

        if not channel_member_ids:
            logger.warning("no_members_in_channel", channel_id=channel_id)
            return ImportResult(imported=0, updated=0, skipped=0, errors=[])

        logger.info(
            "fetched_channel_members",
            channel_id=channel_id,
            member_count=len(channel_member_ids),
        )

        # Fetch user info for each channel member
        for slack_user_id in channel_member_ids:
            try:
                user_response = await client.users_info(user=slack_user_id)
                member = user_response.get("user", {})

                # Skip bots and deactivated users
                if member.get("is_bot") or member.get("deleted"):
                    skipped += 1
                    continue

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

            except SlackApiError as e:
                error_msg = (
                    f"Failed to fetch user {slack_user_id}: {e.response.get('error', str(e))}"
                )
                logger.warning("user_fetch_failed", slack_user_id=slack_user_id, error=str(e))
                errors.append(error_msg)
                skipped += 1

        await session.commit()

        # Now map Harvest IDs to users by email
        harvest_mapped = 0
        try:
            service = HarvestService()
            harvest_users = await service.get_users()

            for hu in harvest_users:
                email = hu.get("email", "").lower()
                if not email:
                    continue

                # Find matching user by email
                result = await session.execute(
                    select(User).where(func.lower(User.email) == email)
                )
                user = result.scalar_one_or_none()

                if user and user.harvest_user_id != hu["id"]:
                    user.harvest_user_id = hu["id"]
                    harvest_mapped += 1
                    logger.info(
                        "mapped_harvest_user",
                        email=email,
                        harvest_id=hu["id"],
                    )

            await session.commit()
            logger.info("harvest_mapping_complete", mapped=harvest_mapped)

        except Exception as e:
            logger.error("harvest_mapping_failed", error=str(e))
            errors.append(f"Harvest mapping failed: {e}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("slack_import_failed", error=str(e))
        errors.append(str(e))
        harvest_mapped = 0

    logger.info(
        "slack_import_complete",
        imported=imported,
        updated=updated,
        skipped=skipped,
        harvest_mapped=harvest_mapped,
    )

    return ImportResult(
        imported=imported,
        updated=updated,
        skipped=skipped,
        harvest_mapped=harvest_mapped,
        errors=errors,
    )


@router.post("/users/import/harvest", response_model=ImportResult)
async def import_harvest_users(
    session: AsyncSession = Depends(get_db),
) -> ImportResult:
    """Import and map users from Harvest."""
    service = HarvestService()

    imported = 0
    updated = 0
    skipped = 0
    errors = []

    try:
        harvest_users = await service.get_users()

        for hu in harvest_users:
            email = hu.get("email", "").lower()
            if not email:
                skipped += 1
                continue

            # Find matching user by email
            result = await session.execute(select(User).where(func.lower(User.email) == email))
            user = result.scalar_one_or_none()

            if user:
                if user.harvest_user_id != hu["id"]:
                    user.harvest_user_id = hu["id"]
                    updated += 1
                else:
                    skipped += 1
            else:
                # No matching user found
                skipped += 1
                logger.debug("no_matching_user_for_harvest", email=email)

        await session.commit()

    except Exception as e:
        logger.error("harvest_import_failed", error=str(e))
        errors.append(str(e))

    logger.info(
        "harvest_import_complete",
        imported=imported,
        updated=updated,
        skipped=skipped,
    )

    return ImportResult(
        imported=imported,
        updated=updated,
        skipped=skipped,
        errors=errors,
    )
