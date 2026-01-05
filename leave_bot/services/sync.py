"""Sync orchestrator for coordinating Calendar and Harvest updates."""

import asyncio
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from leave_bot.database import get_session
from leave_bot.models.leave import LeaveRecord, LeaveStatus
from leave_bot.models.user import User
from leave_bot.services.calendar import CalendarService
from leave_bot.services.harvest import HarvestService
from leave_bot.utils.logging import get_logger

logger = get_logger(__name__)

# Retry configuration
MAX_RETRIES = 3
BASE_DELAY_SECONDS = 5


@dataclass
class SyncResult:
    """Result of a sync operation."""

    success: bool
    calendar_event_id: str | None = None
    harvest_entry_id: int | None = None
    error_message: str | None = None


class SyncService:
    """Orchestrates syncing leave records to external services."""

    def __init__(self) -> None:
        self.calendar = CalendarService()
        self.harvest = HarvestService()
        logger.info("sync_service_initialized")

    async def sync_leave(
        self,
        leave_record: LeaveRecord,
        user: User,
        session: AsyncSession,
    ) -> SyncResult:
        logger.info(
            "syncing_leave",
            leave_id=leave_record.id,
            user_id=user.id,
            date=leave_record.date.isoformat(),
        )

        calendar_event_id: str | None = None
        harvest_entry_id: int | None = None
        errors: list[str] = []

        # Create Calendar event
        try:
            calendar_event_id = await self.calendar.create_event(
                user_name=user.slack_display_name,
                user_email=user.email,
                leave_date=leave_record.date,
                leave_type=leave_record.leave_type,
                timezone=user.slack_timezone,
            )
            leave_record.calendar_event_id = calendar_event_id
        except Exception as e:
            error_msg = f"Calendar sync failed: {e}"
            logger.error("calendar_sync_failed", error=str(e))
            errors.append(error_msg)

        # Create Harvest time entry (only if user has Harvest ID)
        if user.harvest_user_id:
            try:
                harvest_entry_id = await self.harvest.create_time_entry(
                    harvest_user_id=user.harvest_user_id,
                    leave_date=leave_record.date,
                    leave_type=leave_record.leave_type,
                    category=leave_record.leave_category,
                )
                leave_record.harvest_entry_id = harvest_entry_id
            except Exception as e:
                error_msg = f"Harvest sync failed: {e}"
                logger.error("harvest_sync_failed", error=str(e))
                errors.append(error_msg)
        else:
            logger.info("skipping_harvest_no_user_id", user_id=user.id)

        # Update leave record status
        if errors:
            leave_record.status = LeaveStatus.FAILED
            leave_record.error_message = "; ".join(errors)
            leave_record.retry_count += 1
            await session.commit()
            return SyncResult(
                success=False,
                calendar_event_id=calendar_event_id,
                harvest_entry_id=harvest_entry_id,
                error_message=leave_record.error_message,
            )
        else:
            leave_record.status = LeaveStatus.COMPLETED
            leave_record.error_message = None
            await session.commit()
            logger.info(
                "leave_synced",
                leave_id=leave_record.id,
                calendar_event_id=calendar_event_id,
                harvest_entry_id=harvest_entry_id,
            )
            return SyncResult(
                success=True,
                calendar_event_id=calendar_event_id,
                harvest_entry_id=harvest_entry_id,
            )

    async def cancel_leave(
        self,
        leave_record: LeaveRecord,
        session: AsyncSession,
    ) -> SyncResult:
        logger.info(
            "cancelling_leave",
            leave_id=leave_record.id,
            date=leave_record.date.isoformat(),
        )

        errors: list[str] = []

        # Delete Calendar event
        if leave_record.calendar_event_id:
            try:
                await self.calendar.delete_event(leave_record.calendar_event_id)
                leave_record.calendar_event_id = None
            except Exception as e:
                error_msg = f"Calendar delete failed: {e}"
                logger.error("calendar_delete_failed", error=str(e))
                errors.append(error_msg)

        # Delete Harvest entry
        if leave_record.harvest_entry_id:
            try:
                await self.harvest.delete_time_entry(leave_record.harvest_entry_id)
                leave_record.harvest_entry_id = None
            except Exception as e:
                error_msg = f"Harvest delete failed: {e}"
                logger.error("harvest_delete_failed", error=str(e))
                errors.append(error_msg)

        # Update leave record status
        if errors:
            leave_record.status = LeaveStatus.FAILED
            leave_record.error_message = "; ".join(errors)
            await session.commit()
            return SyncResult(success=False, error_message=leave_record.error_message)
        else:
            leave_record.status = LeaveStatus.CANCELLED
            leave_record.error_message = None
            await session.commit()
            logger.info("leave_cancelled", leave_id=leave_record.id)
            return SyncResult(success=True)

    async def retry_failed_leaves(self) -> int:
        async with get_session() as session:
            # Get failed leaves that haven't exceeded retry limit
            result = await session.execute(
                select(LeaveRecord)
                .where(LeaveRecord.status == LeaveStatus.FAILED)
                .where(LeaveRecord.retry_count < MAX_RETRIES)
                .order_by(LeaveRecord.updated_at)
                .limit(10)
            )
            failed_leaves = result.scalars().all()

            if not failed_leaves:
                return 0

            logger.info("retrying_failed_leaves", count=len(failed_leaves))
            success_count = 0

            for leave in failed_leaves:
                # Fetch user
                user_result = await session.execute(select(User).where(User.id == leave.user_id))
                user = user_result.scalar_one_or_none()

                if not user:
                    leave.status = LeaveStatus.CANCELLED
                    leave.error_message = "User not found"
                    continue

                # Exponential backoff delay
                delay = BASE_DELAY_SECONDS * (2**leave.retry_count)
                await asyncio.sleep(delay)

                # Retry sync
                result = await self.sync_leave(leave, user, session)
                if result.success:
                    success_count += 1

            return success_count
