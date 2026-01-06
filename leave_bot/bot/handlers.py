"""Slack message and action handlers."""

import re
import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from slack_bolt.async_app import AsyncApp
from slack_sdk.web.async_client import AsyncWebClient
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert

from leave_bot.bot import blocks
from leave_bot.bot.parser import ThreadMessage, parse_leave_message, validate_parsed_dates
from leave_bot.config import get_settings
from leave_bot.database import get_session
from leave_bot.models.leave import LeaveCategory, LeaveRecord, LeaveStatus, LeaveType
from leave_bot.models.pending_action import ActionStatus, ActionType, PendingAction
from leave_bot.models.user import User
from leave_bot.utils.logging import get_logger

logger = get_logger(__name__)


async def fetch_thread_context(
    client: AsyncWebClient,
    channel_id: str,
    thread_ts: str,
    current_ts: str,
) -> list[ThreadMessage]:
    """Fetch all messages in a thread before the current message."""
    try:
        result = await client.conversations_replies(
            channel=channel_id,
            ts=thread_ts,
            inclusive=True,
        )
        messages = result.get("messages", [])

        thread_context: list[ThreadMessage] = []
        for msg in messages:
            # Skip bot messages
            if msg.get("bot_id") or msg.get("subtype") == "bot_message":
                continue
            # Skip the current message (we don't want to include it twice)
            if msg.get("ts") == current_ts:
                continue
            # Only include messages with text from users
            if msg.get("text") and msg.get("user"):
                thread_context.append(
                    ThreadMessage(
                        text=msg.get("text", ""),
                        user_id=msg.get("user", ""),
                        ts=msg.get("ts", ""),
                    )
                )

        # Sort by timestamp to ensure chronological order
        thread_context.sort(key=lambda m: m.ts)
        return thread_context
    except Exception as e:
        logger.error("fetch_thread_context_error", error=str(e))
        return []


def has_trigger_keyword(text: str, keywords: list[str]) -> bool:
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in keywords)


async def get_user_by_slack_id(slack_user_id: str) -> User | None:
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.slack_user_id == slack_user_id).where(User.is_active.is_(True))
        )
        return result.scalar_one_or_none()


async def check_existing_leaves(
    user_id: int,
    dates: list[date],
) -> list[date]:
    """Check for in-flight leaves only (pending/confirmed). Completed leaves are not
    conflicts since they may have been deleted externally."""
    async with get_session() as session:
        result = await session.execute(
            select(LeaveRecord.date)
            .where(LeaveRecord.user_id == user_id)
            .where(LeaveRecord.date.in_(dates))
            .where(LeaveRecord.status.in_([LeaveStatus.pending, LeaveStatus.confirmed]))
        )
        return list(result.scalars().all())


async def expire_previous_pending_actions(
    user_id: int,
    channel_id: str,
    thread_ts: str | None,
    client: AsyncWebClient,
) -> None:
    """Expire any pending actions for this user in the same thread and update their Slack messages."""
    async with get_session() as session:
        # Find pending actions for this user in the same thread
        query = (
            select(PendingAction)
            .where(PendingAction.user_id == user_id)
            .where(PendingAction.slack_channel_id == channel_id)
            .where(PendingAction.status == ActionStatus.pending)
        )
        if thread_ts:
            # Match actions that are either:
            # - replies in the same thread (slack_thread_ts == thread_ts), or
            # - the original message that started the thread (slack_message_ts == thread_ts)
            query = query.where(
                or_(
                    PendingAction.slack_thread_ts == thread_ts,
                    PendingAction.slack_message_ts == thread_ts,
                )
            )
        else:
            # Top-level message: only match other top-level messages
            query = query.where(PendingAction.slack_thread_ts.is_(None))

        result = await session.execute(query)
        old_actions = result.scalars().all()

        for action in old_actions:
            action.status = ActionStatus.expired

            # Update the old Slack message to show it's superseded
            if action.slack_bot_message_ts and action.slack_channel_id:
                try:
                    await client.chat_update(
                        channel=action.slack_channel_id,
                        ts=action.slack_bot_message_ts,
                        blocks=blocks.build_superseded_message(),
                    )
                except Exception as e:
                    logger.error("failed_to_update_superseded_message", error=str(e))

            logger.info("expired_previous_action", action_id=str(action.id))

        await session.commit()


async def thread_has_completed_action(
    user_id: int,
    channel_id: str,
    thread_ts: str,
) -> bool:
    """Check if this thread already has a confirmed/completed action."""
    async with get_session() as session:
        result = await session.execute(
            select(PendingAction)
            .where(PendingAction.user_id == user_id)
            .where(PendingAction.slack_channel_id == channel_id)
            .where(
                or_(
                    PendingAction.slack_thread_ts == thread_ts,
                    PendingAction.slack_message_ts == thread_ts,
                )
            )
            .where(PendingAction.status.in_([ActionStatus.confirmed, ActionStatus.completed]))
            .limit(1)
        )
        return result.scalar_one_or_none() is not None


async def create_pending_action(
    user_id: int,
    action_type: ActionType,
    payload: dict,
    slack_event_id: str | None,
    slack_message_ts: str | None,
    slack_channel_id: str | None,
    slack_thread_ts: str | None,
) -> PendingAction:
    settings = get_settings()
    expires_at = datetime.now(ZoneInfo("UTC")) + timedelta(
        minutes=settings.pending_action_expiry_minutes
    )

    action = PendingAction(
        user_id=user_id,
        action_type=action_type,
        payload=payload,
        slack_event_id=slack_event_id,
        slack_message_ts=slack_message_ts,
        slack_channel_id=slack_channel_id,
        slack_thread_ts=slack_thread_ts,
        status=ActionStatus.pending,
        expires_at=expires_at,
    )

    async with get_session() as session:
        session.add(action)
        await session.commit()
        await session.refresh(action)
        return action


async def handle_message(
    event: dict,
    say,
    client: AsyncWebClient,
) -> None:
    settings = get_settings()

    # Extract message details
    channel_id = event.get("channel")
    user_id = event.get("user")
    text = event.get("text", "")
    message_ts = event.get("ts")
    thread_ts = event.get("thread_ts")
    event_id = event.get("event_ts") or event.get("client_msg_id")

    # Skip if not in the configured channel
    if channel_id != settings.slack_channel_id:
        return

    # Skip bot messages
    if event.get("bot_id") or event.get("subtype") == "bot_message":
        return

    # Skip if no user id (shouldn't happen but handle gracefully)
    if not user_id:
        return

    # Determine if this is a thread reply
    is_thread_reply = thread_ts is not None and thread_ts != message_ts

    # Skip trigger keyword check for thread replies, require it for top-level messages
    if not is_thread_reply and not has_trigger_keyword(text, settings.trigger_keywords_list):
        logger.debug("no_trigger_keywords", text=text[:50])
        return

    logger.info(
        "processing_leave_message",
        user_id=user_id,
        channel_id=channel_id,
        message_ts=message_ts,
        is_thread_reply=is_thread_reply,
    )

    # Check if user is registered
    user = await get_user_by_slack_id(user_id)
    if not user:
        logger.info("user_not_registered", slack_user_id=user_id)
        await say(
            blocks=blocks.build_not_registered_message(),
            thread_ts=message_ts,
        )
        return

    # Stop listening to thread once a leave has been confirmed
    if is_thread_reply and thread_ts and channel_id:
        if await thread_has_completed_action(user.id, channel_id, thread_ts):
            logger.info("thread_already_completed", thread_ts=thread_ts)
            return

    # Fetch thread context for thread replies
    thread_context: list[ThreadMessage] = []
    if is_thread_reply and thread_ts and channel_id:
        thread_context = await fetch_thread_context(
            client=client,
            channel_id=channel_id,
            thread_ts=thread_ts,
            current_ts=message_ts or "",
        )
        logger.info(
            "fetched_thread_context",
            num_messages=len(thread_context),
            thread_ts=thread_ts,
        )

    # Parse the message with LLM
    parsed = await parse_leave_message(
        message_text=text,
        user_timezone=user.slack_timezone,
        thread_context=thread_context if thread_context else None,
    )

    # If not a leave request, ignore
    if not parsed.is_leave_request:
        logger.info("not_leave_request", text=text[:50])
        return

    # Validate dates
    reference_date = datetime.now(ZoneInfo(user.slack_timezone)).date()
    valid_dates, warnings = validate_parsed_dates(parsed, reference_date)

    if not valid_dates:
        logger.info("no_valid_dates", warnings=warnings)
        await say(
            blocks=blocks.build_clarification_request(),
            thread_ts=message_ts,
        )
        return

    # Update parsed with only valid dates
    parsed.dates = valid_dates

    # Check for conflicts
    date_objects = [date.fromisoformat(d.date) for d in valid_dates]
    conflicting_dates = await check_existing_leaves(user.id, date_objects)
    has_conflicts = len(conflicting_dates) > 0

    # Determine action type
    action_type = ActionType.cancel_leave if parsed.is_cancellation else ActionType.create_leave

    # Expire any previous pending confirmations in this thread
    if channel_id:
        await expire_previous_pending_actions(
            user_id=user.id,
            channel_id=channel_id,
            thread_ts=thread_ts,
            client=client,
        )

    # Create pending action
    action_id = str(uuid.uuid4())[:8]  # Short ID for buttons

    try:
        pending_action = await create_pending_action(
            user_id=user.id,
            action_type=action_type,
            payload={
                "dates": [d.model_dump() for d in valid_dates],
                "action_id": action_id,
                "original_text": text,
                "summary": parsed.original_text_summary,
            },
            slack_event_id=event_id,
            slack_message_ts=message_ts,
            slack_channel_id=channel_id,
            slack_thread_ts=thread_ts,
        )
    except Exception as e:
        # Handle duplicate event (already processed)
        if "unique" in str(e).lower():
            logger.info("duplicate_event", event_id=event_id)
            return
        raise

    # Send confirmation message
    confirmation_blocks = blocks.build_confirmation_message(
        parsed=parsed,
        action_id=str(pending_action.id),
        has_conflicts=has_conflicts,
        conflicting_dates=conflicting_dates,
    )

    if warnings:
        confirmation_blocks.insert(
            -1,
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "⚠️ " + ", ".join(warnings),
                    },
                ],
            },
        )

    response = await say(
        blocks=confirmation_blocks,
        thread_ts=message_ts,
    )

    # Store bot message ts for later updates
    if response and response.get("ts"):
        async with get_session() as session:
            result = await session.execute(
                select(PendingAction).where(PendingAction.id == pending_action.id)
            )
            action = result.scalar_one_or_none()
            if action:
                action.slack_bot_message_ts = response["ts"]
                await session.commit()

    logger.info(
        "confirmation_sent",
        pending_action_id=str(pending_action.id),
        num_dates=len(valid_dates),
    )


async def handle_leave_confirm(ack, body: dict, client: AsyncWebClient) -> None:
    await ack()

    action = body["actions"][0]
    action_id = action["value"]
    user_slack_id = body["user"]["id"]
    channel_id = body["channel"]["id"]
    message_ts = body["message"]["ts"]

    logger.info(
        "leave_confirm_clicked",
        action_id=action_id,
        user_id=user_slack_id,
    )

    async with get_session() as session:
        # Get pending action
        result = await session.execute(select(PendingAction).where(PendingAction.id == action_id))
        pending = result.scalar_one_or_none()

        if not pending:
            logger.error("pending_action_not_found", action_id=action_id)
            return

        # Check if expired
        if pending.status == ActionStatus.expired:
            await client.chat_update(
                channel=channel_id,
                ts=message_ts,
                blocks=blocks.build_expired_message(),
            )
            return

        # Check if already processed
        if pending.status != ActionStatus.pending:
            logger.info("action_already_processed", status=pending.status.value)
            return

        # Verify user owns this action
        user_result = await session.execute(select(User).where(User.id == pending.user_id))
        user = user_result.scalar_one_or_none()

        if not user or user.slack_user_id != user_slack_id:
            logger.warning(
                "user_mismatch", expected=user.slack_user_id if user else None, actual=user_slack_id
            )
            return

        # Update pending action status
        pending.status = ActionStatus.confirmed

        # Create leave records
        payload = pending.payload
        leave_records = []

        for date_info in payload.get("dates", []):
            leave_date = date.fromisoformat(date_info["date"])
            leave_type = LeaveType(date_info.get("type", "full"))
            leave_category = LeaveCategory(date_info.get("category", "vacation"))

            # Use upsert to handle conflicts
            stmt = (
                insert(LeaveRecord)
                .values(
                    user_id=user.id,
                    date=leave_date,
                    leave_type=leave_type,
                    leave_category=leave_category,
                    slack_message_ts=pending.slack_message_ts,
                    slack_channel_id=pending.slack_channel_id,
                    status=LeaveStatus.confirmed,
                )
                .on_conflict_do_update(
                    index_elements=["user_id", "date"],
                    set_={
                        "leave_type": leave_type,
                        "leave_category": leave_category,
                        "status": LeaveStatus.confirmed,
                        "error_message": None,
                    },
                )
                .returning(LeaveRecord)
            )

            result = await session.execute(stmt)
            record = result.scalar_one()
            leave_records.append(record)

        await session.commit()

        logger.info(
            "leave_confirmed",
            pending_action_id=action_id,
            num_records=len(leave_records),
        )

    # Update message to show processing
    await client.chat_update(
        channel=channel_id,
        ts=message_ts,
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "⏳ Processing your leave request...",
                },
            },
        ],
    )


async def handle_leave_cancel(ack, body: dict, client: AsyncWebClient) -> None:
    await ack()

    action = body["actions"][0]
    action_id = action["value"]
    channel_id = body["channel"]["id"]
    message_ts = body["message"]["ts"]

    logger.info("leave_cancel_clicked", action_id=action_id)

    async with get_session() as session:
        # Get and update pending action
        result = await session.execute(select(PendingAction).where(PendingAction.id == action_id))
        pending = result.scalar_one_or_none()

        if pending and pending.status == ActionStatus.pending:
            pending.status = ActionStatus.cancelled
            await session.commit()

    # Update message
    await client.chat_update(
        channel=channel_id,
        ts=message_ts,
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "❌ Leave request cancelled.",
                },
            },
        ],
    )


def register_handlers(app: AsyncApp) -> None:
    @app.event("message")
    async def message_handler(event, say, client):
        await handle_message(event, say, client)

    # Register button action handlers
    @app.action(re.compile(r"leave_confirm_.*"))
    async def confirm_handler(ack, body, client):
        await handle_leave_confirm(ack, body, client)

    @app.action(re.compile(r"leave_cancel_.*"))
    async def cancel_handler(ack, body, client):
        await handle_leave_cancel(ack, body, client)

    logger.info("handlers_registered")
