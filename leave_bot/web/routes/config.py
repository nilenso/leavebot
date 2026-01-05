"""Configuration management endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from leave_bot.database import get_db
from leave_bot.models.configuration import Configuration
from leave_bot.utils.logging import get_logger
from leave_bot.web.schemas import ConfigurationResponse, ConfigurationUpdate

router = APIRouter()
logger = get_logger(__name__)


@router.get("/config", response_model=list[ConfigurationResponse])
async def list_configurations(
    session: AsyncSession = Depends(get_db),
) -> list[ConfigurationResponse]:
    """List all configuration values."""
    result = await session.execute(select(Configuration).order_by(Configuration.key))
    configs = result.scalars().all()
    return [ConfigurationResponse.model_validate(c) for c in configs]


@router.get("/config/{key}", response_model=ConfigurationResponse)
async def get_configuration(
    key: str,
    session: AsyncSession = Depends(get_db),
) -> ConfigurationResponse:
    """Get a configuration value by key."""
    result = await session.execute(select(Configuration).where(Configuration.key == key))
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=404, detail=f"Configuration key '{key}' not found")

    return ConfigurationResponse.model_validate(config)


@router.put("/config/{key}", response_model=ConfigurationResponse)
async def update_configuration(
    key: str,
    config_data: ConfigurationUpdate,
    session: AsyncSession = Depends(get_db),
) -> ConfigurationResponse:
    """Update or create a configuration value."""
    result = await session.execute(select(Configuration).where(Configuration.key == key))
    config = result.scalar_one_or_none()

    if config:
        config.value = config_data.value
    else:
        config = Configuration(key=key, value=config_data.value)
        session.add(config)

    await session.commit()
    await session.refresh(config)

    logger.info("configuration_updated", key=key)
    return ConfigurationResponse.model_validate(config)


@router.delete("/config/{key}", status_code=204)
async def delete_configuration(
    key: str,
    session: AsyncSession = Depends(get_db),
) -> None:
    """Delete a configuration value."""
    result = await session.execute(select(Configuration).where(Configuration.key == key))
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=404, detail=f"Configuration key '{key}' not found")

    await session.delete(config)
    await session.commit()

    logger.info("configuration_deleted", key=key)
