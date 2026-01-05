"""Health check endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from leave_bot.bot.app import check_slack_connection
from leave_bot.database import get_db
from leave_bot.services.calendar import CalendarService
from leave_bot.services.harvest import HarvestService
from leave_bot.utils.logging import get_logger
from leave_bot.web.schemas import HealthResponse, ServiceHealth

router = APIRouter()
logger = get_logger(__name__)


async def check_database(session: AsyncSession) -> ServiceHealth:
    try:
        await session.execute(text("SELECT 1"))
        return ServiceHealth(status="healthy")
    except Exception as e:
        logger.error("database_health_check_failed", error=str(e))
        return ServiceHealth(status="unhealthy", message=str(e))


async def check_calendar() -> ServiceHealth:
    try:
        service = CalendarService()
        healthy = await service.check_connection()
        if healthy:
            return ServiceHealth(status="healthy")
        return ServiceHealth(status="unhealthy", message="Connection check failed")
    except Exception as e:
        logger.error("calendar_health_check_failed", error=str(e))
        return ServiceHealth(status="unhealthy", message=str(e))


async def check_harvest() -> ServiceHealth:
    try:
        service = HarvestService()
        healthy = await service.check_connection()
        if healthy:
            return ServiceHealth(status="healthy")
        return ServiceHealth(status="unhealthy", message="Connection check failed")
    except Exception as e:
        logger.error("harvest_health_check_failed", error=str(e))
        return ServiceHealth(status="unhealthy", message=str(e))


async def check_slack() -> ServiceHealth:
    try:
        healthy = await check_slack_connection()
        if healthy:
            return ServiceHealth(status="healthy")
        return ServiceHealth(status="unhealthy", message="Connection check failed")
    except Exception as e:
        logger.error("slack_health_check_failed", error=str(e))
        return ServiceHealth(status="unhealthy", message=str(e))


@router.get("/health", response_model=HealthResponse)
async def health_check(session: AsyncSession = Depends(get_db)) -> HealthResponse:
    """Get overall health status of all services."""
    db_health = await check_database(session)
    slack_health = await check_slack()
    calendar_health = await check_calendar()
    harvest_health = await check_harvest()

    # Determine overall status
    all_healthy = all(
        h.status == "healthy" for h in [db_health, slack_health, calendar_health, harvest_health]
    )

    return HealthResponse(
        status="healthy" if all_healthy else "degraded",
        database=db_health,
        slack=slack_health,
        calendar=calendar_health,
        harvest=harvest_health,
    )


@router.get("/health/database", response_model=ServiceHealth)
async def database_health(session: AsyncSession = Depends(get_db)) -> ServiceHealth:
    """Check database health."""
    return await check_database(session)


@router.get("/health/slack", response_model=ServiceHealth)
async def slack_health() -> ServiceHealth:
    """Check Slack health."""
    return await check_slack()


@router.get("/health/calendar", response_model=ServiceHealth)
async def calendar_health() -> ServiceHealth:
    """Check Google Calendar health."""
    return await check_calendar()


@router.get("/health/harvest", response_model=ServiceHealth)
async def harvest_health() -> ServiceHealth:
    """Check Harvest health."""
    return await check_harvest()
