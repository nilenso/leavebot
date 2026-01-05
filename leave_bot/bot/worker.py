"""Background worker for processing pending actions and retries."""

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from slack_sdk.web.async_client import AsyncWebClient
from sqlalchemy import select

from leave_bot.bot import blocks
from leave_bot.config import get_settings
from leave_bot.database import get_session
from leave_bot.models.leave import LeaveRecord, LeaveStatus
from leave_bot.models.pending_action import ActionStatus, ActionType, PendingAction
from leave_bot.models.user import User
from leave_bot.services.sync import SyncService
from leave_bot.utils.logging import get_logger

logger = get_logger(__name__)

# Worker configuration
POLL_INTERVAL_SECONDS = 5
EXPIRE_CHECK_INTERVAL_SECONDS = 60


class Worker:
    """Background worker for processing leave actions."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.sync_service = SyncService()
        self.slack_client = AsyncWebClient(token=self.settings.slack_bot_token)
        self.running = False
        logger.info("worker_initialized")

    async def process_confirmed_actions(self) -> int:
        async with get_session() as session:
            # Get confirmed pending actions
            result = await session.execute(
                select(PendingAction)
                .where(PendingAction.status == ActionStatus.confirmed)
                .order_by(PendingAction.created_at)
                .limit(10)
            )
            actions = result.scalars().all()

            if not actions:
                return 0

            processed = 0

            for action in actions:
                try:
                    # Mark as processing
                    action.status = ActionStatus.processing
                    await session.commit()

                    # Get user
                    user_result = await session.execute(
                        select(User).where(User.id == action.user_id)
                    )
                    user = user_result.scalar_one_or_none()

                    if not user:
                        action.status = ActionStatus.completed
                        logger.warning("user_not_found_for_action", action_id=str(action.id))
                        continue

                    # Process based on action type
                    if action.action_type == ActionType.create_leave:
                        await self._process_create_leave(action, user, session)
                    elif action.action_type == ActionType.cancel_leave:
                        await self._process_cancel_leave(action, user, session)

                    action.status = ActionStatus.completed
                    processed += 1

                except Exception as e:
                    logger.error(
                        "action_processing_failed",
                        action_id=str(action.id),
                        error=str(e),
                    )
                    action.status = ActionStatus.confirmed  # Allow retry
                    await session.rollback()

            await session.commit()
            return processed

    async def _process_create_leave(
        self,
        action: PendingAction,
        user: User,
        session,
    ) -> None:
        payload = action.payload
        dates = payload.get("dates", [])

        logger.info(
            "processing_create_leave",
            action_id=str(action.id),
            num_dates=len(dates),
        )

        successful_records = []
        failed_records = []

        for date_info in dates:
            # Get leave record
            from datetime import date as date_type

            leave_date = date_type.fromisoformat(date_info["date"])

            result = await session.execute(
                select(LeaveRecord)
                .where(LeaveRecord.user_id == user.id)
                .where(LeaveRecord.date == leave_date)
                .where(LeaveRecord.status == LeaveStatus.confirmed)
            )
            record = result.scalar_one_or_none()

            if not record:
                logger.warning("leave_record_not_found", date=date_info["date"])
                continue

            # Sync the leave
            sync_result = await self.sync_service.sync_leave(record, user, session)

            if sync_result.success:
                successful_records.append(record)
            else:
                failed_records.append(record)

        # Update Slack message
        if action.slack_channel_id and action.slack_message_ts:
            try:
                # Find the bot's reply message (thread)
                response = await self.slack_client.conversations_replies(
                    channel=action.slack_channel_id,
                    ts=action.slack_message_ts,
                    limit=10,
                )

                # Find the last bot message in thread
                bot_message_ts = None
                for msg in response.get("messages", []):
                    if msg.get("bot_id"):
                        bot_message_ts = msg.get("ts")

                if bot_message_ts:
                    if failed_records:
                        error_msg = f"Failed to sync {len(failed_records)} leave(s)"
                        await self.slack_client.chat_update(
                            channel=action.slack_channel_id,
                            ts=bot_message_ts,
                            blocks=blocks.build_error_message(error_msg, retry_available=True),
                        )
                    else:
                        await self.slack_client.chat_update(
                            channel=action.slack_channel_id,
                            ts=bot_message_ts,
                            blocks=blocks.build_success_message(successful_records),
                        )
            except Exception as e:
                logger.error("slack_update_failed", error=str(e))

    async def _process_cancel_leave(
        self,
        action: PendingAction,
        user: User,
        session,
    ) -> None:
        payload = action.payload
        dates = payload.get("dates", [])

        logger.info(
            "processing_cancel_leave",
            action_id=str(action.id),
            num_dates=len(dates),
        )

        for date_info in dates:
            from datetime import date as date_type

            leave_date = date_type.fromisoformat(date_info["date"])

            result = await session.execute(
                select(LeaveRecord)
                .where(LeaveRecord.user_id == user.id)
                .where(LeaveRecord.date == leave_date)
                .where(LeaveRecord.status.in_([LeaveStatus.confirmed, LeaveStatus.completed]))
            )
            record = result.scalar_one_or_none()

            if record:
                await self.sync_service.cancel_leave(record, session)

    async def expire_old_actions(self) -> int:
        now = datetime.now(ZoneInfo("UTC"))

        async with get_session() as session:
            # Get expired actions
            result = await session.execute(
                select(PendingAction)
                .where(PendingAction.status == ActionStatus.pending)
                .where(PendingAction.expires_at < now)
            )
            expired_actions = result.scalars().all()

            if not expired_actions:
                return 0

            for action in expired_actions:
                action.status = ActionStatus.expired

                # Update Slack message to disable buttons
                if action.slack_channel_id and action.slack_message_ts:
                    try:
                        response = await self.slack_client.conversations_replies(
                            channel=action.slack_channel_id,
                            ts=action.slack_message_ts,
                            limit=10,
                        )

                        for msg in response.get("messages", []):
                            if msg.get("bot_id"):
                                await self.slack_client.chat_update(
                                    channel=action.slack_channel_id,
                                    ts=msg["ts"],
                                    blocks=blocks.build_expired_message(),
                                )
                                break
                    except Exception as e:
                        logger.error("slack_expire_update_failed", error=str(e))

            await session.commit()
            logger.info("expired_actions", count=len(expired_actions))
            return len(expired_actions)

    async def retry_failed_syncs(self) -> int:
        return await self.sync_service.retry_failed_leaves()

    async def run(self) -> None:
        self.running = True
        logger.info("worker_started")

        expire_counter = 0

        while self.running:
            try:
                # Process confirmed actions
                processed = await self.process_confirmed_actions()
                if processed > 0:
                    logger.info("processed_actions", count=processed)

                # Retry failed syncs occasionally
                retried = await self.retry_failed_syncs()
                if retried > 0:
                    logger.info("retried_syncs", count=retried)

                # Expire old actions less frequently
                expire_counter += POLL_INTERVAL_SECONDS
                if expire_counter >= EXPIRE_CHECK_INTERVAL_SECONDS:
                    await self.expire_old_actions()
                    expire_counter = 0

            except Exception as e:
                logger.error("worker_error", error=str(e))

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    def stop(self) -> None:
        self.running = False
        logger.info("worker_stopping")


async def start_worker() -> Worker:
    worker = Worker()
    asyncio.create_task(worker.run())
    return worker
