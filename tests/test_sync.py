"""Tests for sync service."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from leave_bot.models.leave import LeaveCategory, LeaveRecord, LeaveStatus, LeaveType
from leave_bot.models.user import User
from leave_bot.services.sync import SyncResult, SyncService


class TestSyncResult:
    """Tests for SyncResult dataclass."""

    def test_successful_result(self):
        """Test successful sync result."""
        result = SyncResult(
            success=True,
            calendar_event_id="event123",
            harvest_entry_id=456,
        )

        assert result.success is True
        assert result.calendar_event_id == "event123"
        assert result.harvest_entry_id == 456
        assert result.error_message is None

    def test_failed_result(self):
        """Test failed sync result."""
        result = SyncResult(
            success=False,
            error_message="Calendar API error",
        )

        assert result.success is False
        assert result.error_message == "Calendar API error"


class TestSyncService:
    """Tests for SyncService."""

    @pytest.fixture
    def mock_calendar_service(self):
        """Create a mock calendar service."""
        service = MagicMock()
        service.create_event = AsyncMock(return_value="event123")
        service.delete_event = AsyncMock(return_value=True)
        service.check_connection = AsyncMock(return_value=True)
        return service

    @pytest.fixture
    def mock_harvest_service(self):
        """Create a mock harvest service."""
        service = MagicMock()
        service.create_time_entry = AsyncMock(return_value=456)
        service.delete_time_entry = AsyncMock(return_value=True)
        service.check_connection = AsyncMock(return_value=True)
        return service

    @pytest.fixture
    def sample_user(self):
        """Create a sample user."""
        return User(
            id=1,
            slack_user_id="U12345678",
            slack_display_name="Test User",
            email="test@example.com",
            slack_timezone="Asia/Kolkata",
            harvest_user_id=12345,
            is_active=True,
        )

    @pytest.fixture
    def sample_leave(self, sample_user):
        """Create a sample leave record."""
        return LeaveRecord(
            id=1,
            user_id=sample_user.id,
            date=date(2026, 1, 5),
            leave_type=LeaveType.FULL,
            leave_category=LeaveCategory.VACATION,
            status=LeaveStatus.CONFIRMED,
            retry_count=0,
        )

    @pytest.mark.asyncio
    async def test_sync_leave_success(
        self,
        mock_calendar_service,
        mock_harvest_service,
        sample_user,
        sample_leave,
    ):
        """Test successful leave sync."""
        with (
            patch("leave_bot.services.sync.CalendarService", return_value=mock_calendar_service),
            patch("leave_bot.services.sync.HarvestService", return_value=mock_harvest_service),
        ):
            sync_service = SyncService()

            # Mock session
            mock_session = MagicMock()
            mock_session.commit = AsyncMock()

            result = await sync_service.sync_leave(sample_leave, sample_user, mock_session)

            assert result.success is True
            assert result.calendar_event_id == "event123"
            assert result.harvest_entry_id == 456
            assert sample_leave.status == LeaveStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_sync_leave_calendar_failure(
        self,
        mock_calendar_service,
        mock_harvest_service,
        sample_user,
        sample_leave,
    ):
        """Test sync when calendar fails."""
        mock_calendar_service.create_event = AsyncMock(side_effect=Exception("Calendar error"))

        with (
            patch("leave_bot.services.sync.CalendarService", return_value=mock_calendar_service),
            patch("leave_bot.services.sync.HarvestService", return_value=mock_harvest_service),
        ):
            sync_service = SyncService()

            mock_session = MagicMock()
            mock_session.commit = AsyncMock()

            result = await sync_service.sync_leave(sample_leave, sample_user, mock_session)

            assert result.success is False
            assert result.error_message is not None
            assert "Calendar" in result.error_message
            assert sample_leave.status == LeaveStatus.FAILED

    @pytest.mark.asyncio
    async def test_sync_leave_harvest_failure(
        self,
        mock_calendar_service,
        mock_harvest_service,
        sample_user,
        sample_leave,
    ):
        """Test sync when Harvest fails."""
        mock_harvest_service.create_time_entry = AsyncMock(side_effect=Exception("Harvest error"))

        with (
            patch("leave_bot.services.sync.CalendarService", return_value=mock_calendar_service),
            patch("leave_bot.services.sync.HarvestService", return_value=mock_harvest_service),
        ):
            sync_service = SyncService()

            mock_session = MagicMock()
            mock_session.commit = AsyncMock()

            result = await sync_service.sync_leave(sample_leave, sample_user, mock_session)

            assert result.success is False
            assert result.error_message is not None
            assert "Harvest" in result.error_message
            # Calendar event should still be created
            assert sample_leave.calendar_event_id == "event123"

    @pytest.mark.asyncio
    async def test_sync_leave_no_harvest_user(
        self,
        mock_calendar_service,
        mock_harvest_service,
        sample_leave,
    ):
        """Test sync for user without Harvest ID."""
        user_no_harvest = User(
            id=1,
            slack_user_id="U12345678",
            slack_display_name="Test User",
            email="test@example.com",
            slack_timezone="Asia/Kolkata",
            harvest_user_id=None,  # No Harvest ID
            is_active=True,
        )

        with (
            patch("leave_bot.services.sync.CalendarService", return_value=mock_calendar_service),
            patch("leave_bot.services.sync.HarvestService", return_value=mock_harvest_service),
        ):
            sync_service = SyncService()

            mock_session = MagicMock()
            mock_session.commit = AsyncMock()

            result = await sync_service.sync_leave(sample_leave, user_no_harvest, mock_session)

            assert result.success is True
            assert result.calendar_event_id == "event123"
            assert result.harvest_entry_id is None  # No Harvest entry
            mock_harvest_service.create_time_entry.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancel_leave_success(
        self,
        mock_calendar_service,
        mock_harvest_service,
        sample_leave,
    ):
        """Test successful leave cancellation."""
        sample_leave.calendar_event_id = "event123"
        sample_leave.harvest_entry_id = 456
        sample_leave.status = LeaveStatus.COMPLETED

        with (
            patch("leave_bot.services.sync.CalendarService", return_value=mock_calendar_service),
            patch("leave_bot.services.sync.HarvestService", return_value=mock_harvest_service),
        ):
            sync_service = SyncService()

            mock_session = MagicMock()
            mock_session.commit = AsyncMock()

            result = await sync_service.cancel_leave(sample_leave, mock_session)

            assert result.success is True
            assert sample_leave.status == LeaveStatus.CANCELLED
            mock_calendar_service.delete_event.assert_called_once_with("event123")
            mock_harvest_service.delete_time_entry.assert_called_once_with(456)

    @pytest.mark.asyncio
    async def test_cancel_leave_partial_failure(
        self,
        mock_calendar_service,
        mock_harvest_service,
        sample_leave,
    ):
        """Test cancellation with partial failure."""
        sample_leave.calendar_event_id = "event123"
        sample_leave.harvest_entry_id = 456
        sample_leave.status = LeaveStatus.COMPLETED

        mock_harvest_service.delete_time_entry = AsyncMock(side_effect=Exception("Harvest error"))

        with (
            patch("leave_bot.services.sync.CalendarService", return_value=mock_calendar_service),
            patch("leave_bot.services.sync.HarvestService", return_value=mock_harvest_service),
        ):
            sync_service = SyncService()

            mock_session = MagicMock()
            mock_session.commit = AsyncMock()

            result = await sync_service.cancel_leave(sample_leave, mock_session)

            assert result.success is False
            assert result.error_message is not None
            assert "Harvest" in result.error_message
            # Calendar event should still be deleted
            mock_calendar_service.delete_event.assert_called_once()


class TestCalendarService:
    """Tests for CalendarService."""

    @pytest.mark.asyncio
    async def test_create_full_day_event(self):
        """Test creating a full-day calendar event."""
        from leave_bot.services.calendar import CalendarService

        with (
            patch("leave_bot.services.calendar.service_account"),
            patch("leave_bot.services.calendar.build") as mock_build,
            patch("leave_bot.services.calendar.get_settings") as mock_settings,
        ):
            mock_settings.return_value.google_service_account_info = {"type": "service_account"}
            mock_settings.return_value.google_calendar_id = "cal123"

            mock_service = MagicMock()
            mock_build.return_value = mock_service
            mock_service.events.return_value.insert.return_value.execute.return_value = {
                "id": "event123"
            }

            service = CalendarService()
            event_id = await service.create_event(
                user_name="Test User",
                user_email="test@example.com",
                leave_date=date(2026, 1, 5),
                leave_type=LeaveType.FULL,
            )

            assert event_id == "event123"

    @pytest.mark.asyncio
    async def test_create_half_day_event(self):
        """Test creating a half-day calendar event."""
        from leave_bot.services.calendar import CalendarService

        with (
            patch("leave_bot.services.calendar.service_account"),
            patch("leave_bot.services.calendar.build") as mock_build,
            patch("leave_bot.services.calendar.get_settings") as mock_settings,
        ):
            mock_settings.return_value.google_service_account_info = {"type": "service_account"}
            mock_settings.return_value.google_calendar_id = "cal123"

            mock_service = MagicMock()
            mock_build.return_value = mock_service
            mock_service.events.return_value.insert.return_value.execute.return_value = {
                "id": "event456"
            }

            service = CalendarService()
            event_id = await service.create_event(
                user_name="Test User",
                user_email=None,
                leave_date=date(2026, 1, 5),
                leave_type=LeaveType.HALF_PM,
            )

            assert event_id == "event456"


class TestHarvestService:
    """Tests for HarvestService."""

    @pytest.mark.asyncio
    async def test_create_time_entry(self):
        """Test creating a Harvest time entry."""
        from leave_bot.services.harvest import HarvestService

        with (
            patch("leave_bot.services.harvest.get_settings") as mock_settings,
            patch("httpx.AsyncClient") as mock_client,
        ):
            mock_settings.return_value.harvest_access_token = "token"
            mock_settings.return_value.harvest_account_id = "123"
            mock_settings.return_value.harvest_project_id = 1
            mock_settings.return_value.harvest_vacation_task_id = 2
            mock_settings.return_value.harvest_sick_task_id = 3

            mock_response = MagicMock()
            mock_response.json.return_value = {"id": 789}
            mock_response.raise_for_status = MagicMock()

            mock_client_instance = MagicMock()
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock()
            mock_client_instance.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_client_instance

            service = HarvestService()
            entry_id = await service.create_time_entry(
                harvest_user_id=12345,
                leave_date=date(2026, 1, 5),
                leave_type=LeaveType.FULL,
                category=LeaveCategory.VACATION,
            )

            assert entry_id == 789
