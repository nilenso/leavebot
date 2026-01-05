"""Leave management endpoints."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from leave_bot.database import get_db
from leave_bot.models.leave import LeaveRecord, LeaveStatus
from leave_bot.services.sync import SyncService
from leave_bot.utils.logging import get_logger
from leave_bot.web.schemas import (
    LeaveRecordResponse,
    LeaveRecordWithUser,
    PaginatedResponse,
    UserResponse,
)

router = APIRouter()
logger = get_logger(__name__)


@router.get("/leaves", response_model=PaginatedResponse[LeaveRecordWithUser])
async def list_leaves(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    user_id: int | None = None,
    status: LeaveStatus | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    session: AsyncSession = Depends(get_db),
) -> PaginatedResponse[LeaveRecordWithUser]:
    """List leave records with pagination and filters."""
    # Build base query
    query = select(LeaveRecord).options(selectinload(LeaveRecord.user))
    count_query = select(func.count()).select_from(LeaveRecord)

    # Apply filters
    if user_id:
        query = query.where(LeaveRecord.user_id == user_id)
        count_query = count_query.where(LeaveRecord.user_id == user_id)

    if status:
        query = query.where(LeaveRecord.status == status)
        count_query = count_query.where(LeaveRecord.status == status)

    if start_date:
        query = query.where(LeaveRecord.date >= start_date)
        count_query = count_query.where(LeaveRecord.date >= start_date)

    if end_date:
        query = query.where(LeaveRecord.date <= end_date)
        count_query = count_query.where(LeaveRecord.date <= end_date)

    # Get total count
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.order_by(LeaveRecord.date.desc()).offset(offset).limit(page_size)

    # Execute query
    result = await session.execute(query)
    leaves = result.scalars().all()

    # Build response with user data
    items = []
    for leave in leaves:
        leave_dict = LeaveRecordResponse.model_validate(leave).model_dump()
        leave_dict["user"] = UserResponse.model_validate(leave.user)
        items.append(LeaveRecordWithUser(**leave_dict))

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/leaves/{leave_id}", response_model=LeaveRecordWithUser)
async def get_leave(
    leave_id: int,
    session: AsyncSession = Depends(get_db),
) -> LeaveRecordWithUser:
    """Get a leave record by ID."""
    result = await session.execute(
        select(LeaveRecord)
        .options(selectinload(LeaveRecord.user))
        .where(LeaveRecord.id == leave_id)
    )
    leave = result.scalar_one_or_none()

    if not leave:
        raise HTTPException(status_code=404, detail="Leave record not found")

    leave_dict = LeaveRecordResponse.model_validate(leave).model_dump()
    leave_dict["user"] = UserResponse.model_validate(leave.user)
    return LeaveRecordWithUser(**leave_dict)


@router.post("/leaves/{leave_id}/retry", response_model=LeaveRecordResponse)
async def retry_leave_sync(
    leave_id: int,
    session: AsyncSession = Depends(get_db),
) -> LeaveRecordResponse:
    """Retry syncing a failed leave record."""
    result = await session.execute(
        select(LeaveRecord)
        .options(selectinload(LeaveRecord.user))
        .where(LeaveRecord.id == leave_id)
    )
    leave = result.scalar_one_or_none()

    if not leave:
        raise HTTPException(status_code=404, detail="Leave record not found")

    if leave.status != LeaveStatus.FAILED:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retry leave with status {leave.status.value}",
        )

    # Reset status to confirmed for retry
    leave.status = LeaveStatus.CONFIRMED
    leave.error_message = None
    await session.commit()

    logger.info("leave_retry_queued", leave_id=leave_id)

    # Trigger immediate sync
    sync_service = SyncService()
    await sync_service.sync_leave(leave, leave.user, session)

    await session.refresh(leave)
    return LeaveRecordResponse.model_validate(leave)


@router.delete("/leaves/{leave_id}", status_code=204)
async def delete_leave(
    leave_id: int,
    session: AsyncSession = Depends(get_db),
) -> None:
    """Delete a leave record and cancel sync."""
    result = await session.execute(select(LeaveRecord).where(LeaveRecord.id == leave_id))
    leave = result.scalar_one_or_none()

    if not leave:
        raise HTTPException(status_code=404, detail="Leave record not found")

    # Cancel sync first
    if leave.status == LeaveStatus.COMPLETED:
        sync_service = SyncService()
        await sync_service.cancel_leave(leave, session)

    # Delete the record
    await session.delete(leave)
    await session.commit()

    logger.info("leave_deleted", leave_id=leave_id)


@router.get("/leaves/stats/summary")
async def get_leave_stats(
    start_date: date | None = None,
    end_date: date | None = None,
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Get leave statistics summary."""
    # Build base query
    query = select(
        LeaveRecord.status,
        func.count(LeaveRecord.id).label("count"),
    ).group_by(LeaveRecord.status)

    if start_date:
        query = query.where(LeaveRecord.date >= start_date)
    if end_date:
        query = query.where(LeaveRecord.date <= end_date)

    result = await session.execute(query)
    stats: dict[str, int] = {row[0].value: int(row[1]) for row in result}

    # Get total leaves by category
    category_query = (
        select(
            LeaveRecord.leave_category,
            func.count(LeaveRecord.id).label("count"),
        )
        .where(LeaveRecord.status == LeaveStatus.COMPLETED)
        .group_by(LeaveRecord.leave_category)
    )

    if start_date:
        category_query = category_query.where(LeaveRecord.date >= start_date)
    if end_date:
        category_query = category_query.where(LeaveRecord.date <= end_date)

    category_result = await session.execute(category_query)
    categories: dict[str, int] = {row[0].value: int(row[1]) for row in category_result}

    return {
        "by_status": stats,
        "by_category": categories,
        "total": sum(stats.values()),
    }
