"""Harvest API service for creating and managing time entries."""

from datetime import date
from typing import Any

import httpx

from leave_bot.config import get_settings
from leave_bot.models.leave import LeaveCategory, LeaveType
from leave_bot.utils.logging import get_logger

logger = get_logger(__name__)

# Harvest API base URL
HARVEST_API_BASE = "https://api.harvestapp.com/v2"

# Hours for leave types
FULL_DAY_HOURS = 8.0
HALF_DAY_HOURS = 4.0


class HarvestService:
    """Harvest API client for time entry management."""

    def __init__(self) -> None:
        settings = get_settings()

        self.access_token = settings.harvest_access_token
        self.account_id = settings.harvest_account_id
        self.project_id = settings.harvest_project_id
        self.vacation_task_id = settings.harvest_vacation_task_id
        self.sick_task_id = settings.harvest_sick_task_id

        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Harvest-Account-Id": self.account_id,
            "User-Agent": "Nilenso Leave Bot (leavebot@nilenso.com)",
            "Content-Type": "application/json",
        }

        logger.info("harvest_service_initialized", project_id=self.project_id)

    def _get_task_id(self, category: LeaveCategory) -> int:
        if category == LeaveCategory.sick:
            return self.sick_task_id
        return self.vacation_task_id

    def _get_hours(self, leave_type: LeaveType) -> float:
        if leave_type == LeaveType.full:
            return FULL_DAY_HOURS
        return HALF_DAY_HOURS

    async def create_time_entry(
        self,
        harvest_user_id: int,
        leave_date: date,
        leave_type: LeaveType,
        category: LeaveCategory,
        notes: str | None = None,
    ) -> int:
        task_id = self._get_task_id(category)
        hours = self._get_hours(leave_type)

        # Build notes string
        if notes is None:
            if leave_type == LeaveType.full:
                notes = f"Leave ({category.value})"
            elif leave_type == LeaveType.half_am:
                notes = f"Leave - Morning ({category.value})"
            else:
                notes = f"Leave - Afternoon ({category.value})"

        payload: dict[str, Any] = {
            "user_id": harvest_user_id,
            "project_id": self.project_id,
            "task_id": task_id,
            "spent_date": leave_date.isoformat(),
            "hours": hours,
            "notes": notes,
        }

        logger.info(
            "creating_harvest_entry",
            harvest_user_id=harvest_user_id,
            leave_date=leave_date.isoformat(),
            hours=hours,
            category=category.value,
        )

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{HARVEST_API_BASE}/time_entries",
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        entry_id = data["id"]
        logger.info("harvest_entry_created", entry_id=entry_id)
        return entry_id

    async def delete_time_entry(self, entry_id: int) -> bool:
        logger.info("deleting_harvest_entry", entry_id=entry_id)

        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{HARVEST_API_BASE}/time_entries/{entry_id}",
                headers=self.headers,
            )
            response.raise_for_status()

        logger.info("harvest_entry_deleted", entry_id=entry_id)
        return True

    async def get_users(self) -> list[dict[str, Any]]:
        users = []
        page = 1

        async with httpx.AsyncClient() as client:
            while True:
                response = await client.get(
                    f"{HARVEST_API_BASE}/users",
                    headers=self.headers,
                    params={"page": page, "per_page": 100, "is_active": "true"},
                )
                response.raise_for_status()
                data = response.json()

                users.extend(data["users"])

                if data["page"] >= data["total_pages"]:
                    break
                page += 1

        logger.info("fetched_harvest_users", count=len(users))
        return users

    async def check_connection(self) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{HARVEST_API_BASE}/users/me",
                    headers=self.headers,
                )
                response.raise_for_status()
                return True
        except httpx.HTTPStatusError as e:
            logger.error("harvest_health_check_failed", error=str(e))
            return False
