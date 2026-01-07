"""Tests for web API routes."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from slack_sdk.errors import SlackApiError

from leave_bot.models.user import User


class TestUserImportEndpoint:
    """Tests for /api/users/import/slack endpoint."""

    @pytest.fixture
    def mock_slack_client(self):
        """Create a mock Slack client."""
        client = MagicMock()
        return client

    @pytest.fixture
    def mock_harvest_service(self):
        """Create a mock Harvest service."""
        service = MagicMock()
        service.get_users = AsyncMock(return_value=[])
        return service

    @pytest.mark.asyncio
    async def test_import_slack_also_maps_harvest_ids(self):
        """Test that importing from Slack also maps Harvest IDs by email."""
        from leave_bot.web.routes.users import import_slack_users

        # Mock Slack API responses
        mock_conversations_members = AsyncMock(
            return_value={
                "members": ["U123"],
                "response_metadata": {"next_cursor": ""},
            }
        )

        mock_users_info = AsyncMock(
            return_value={
                "user": {
                    "id": "U123",
                    "is_bot": False,
                    "deleted": False,
                    "tz": "Asia/Kolkata",
                    "profile": {
                        "display_name": "Test User",
                        "email": "test@example.com",
                    },
                }
            }
        )

        # Mock Harvest API response - user with matching email
        mock_harvest_users = [
            {"id": 12345, "email": "test@example.com"},
        ]

        # Track what harvest_user_id gets set to
        captured_harvest_id = None

        # Create mock user that gets "found" in second query
        mock_user = MagicMock(spec=User)
        mock_user.harvest_user_id = None

        def capture_harvest_id(value):
            nonlocal captured_harvest_id
            captured_harvest_id = value

        mock_user.harvest_user_id = property(
            lambda self: captured_harvest_id,
            lambda self, v: capture_harvest_id(v),
        )

        # Create a mock session
        mock_session = MagicMock()
        mock_session.commit = AsyncMock()

        # First execute: check existing user (returns None - new user)
        # Second execute: find user by email for Harvest mapping
        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # First call: check if user exists by slack_user_id
                result.scalar_one_or_none.return_value = None
            else:
                # Second call: find user by email for Harvest mapping
                result.scalar_one_or_none.return_value = mock_user
            return result

        mock_session.execute = mock_execute
        mock_session.add = MagicMock()

        with (
            patch("slack_sdk.web.async_client.AsyncWebClient") as mock_client_class,
            patch("leave_bot.web.routes.users.HarvestService") as mock_harvest_class,
            patch("leave_bot.web.routes.users.get_settings") as mock_settings,
        ):
            # Setup mocks
            mock_client = MagicMock()
            mock_client.conversations_members = mock_conversations_members
            mock_client.users_info = mock_users_info
            mock_client_class.return_value = mock_client

            mock_harvest = MagicMock()
            mock_harvest.get_users = AsyncMock(return_value=mock_harvest_users)
            mock_harvest_class.return_value = mock_harvest

            mock_settings.return_value.slack_bot_token = "test-token"
            mock_settings.return_value.slack_channel_id = "C123"

            # Call the endpoint
            result = await import_slack_users(session=mock_session)

            # Verify Harvest service was called to get users
            mock_harvest.get_users.assert_called_once()

            # Verify harvest_mapped is reported
            assert result.harvest_mapped == 1

    @pytest.mark.asyncio
    async def test_import_slack_harvest_failure_reported_in_errors(self):
        """Test that Harvest API failures are reported in errors but don't fail import."""
        from leave_bot.web.routes.users import import_slack_users

        # Mock Slack API responses
        mock_conversations_members = AsyncMock(
            return_value={
                "members": ["U123"],
                "response_metadata": {"next_cursor": ""},
            }
        )

        mock_users_info = AsyncMock(
            return_value={
                "user": {
                    "id": "U123",
                    "is_bot": False,
                    "deleted": False,
                    "tz": "Asia/Kolkata",
                    "profile": {
                        "display_name": "Test User",
                        "email": "test@example.com",
                    },
                }
            }
        )

        mock_session = MagicMock()
        mock_session.commit = AsyncMock()

        async def mock_execute(query):
            result = MagicMock()
            result.scalar_one_or_none.return_value = None  # New user
            return result

        mock_session.execute = mock_execute
        mock_session.add = MagicMock()

        with (
            patch("slack_sdk.web.async_client.AsyncWebClient") as mock_client_class,
            patch("leave_bot.web.routes.users.HarvestService") as mock_harvest_class,
            patch("leave_bot.web.routes.users.get_settings") as mock_settings,
        ):
            # Setup mocks
            mock_client = MagicMock()
            mock_client.conversations_members = mock_conversations_members
            mock_client.users_info = mock_users_info
            mock_client_class.return_value = mock_client

            # Harvest fails with HTTP error
            mock_request = httpx.Request("GET", "https://api.harvestapp.com/v2/users")
            mock_response = httpx.Response(500, request=mock_request)
            mock_harvest = MagicMock()
            mock_harvest.get_users = AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "Server error", request=mock_request, response=mock_response
                )
            )
            mock_harvest_class.return_value = mock_harvest

            mock_settings.return_value.slack_bot_token = "test-token"
            mock_settings.return_value.slack_channel_id = "C123"

            # Call the endpoint
            result = await import_slack_users(session=mock_session)

            # Import should succeed (1 user imported from Slack)
            assert result.imported == 1
            # Harvest mapping should be 0 due to error
            assert result.harvest_mapped == 0
            # Error should be reported
            assert len(result.errors) == 1
            assert "Harvest mapping failed" in result.errors[0]


class TestImportResultSchema:
    """Tests for ImportResult schema."""

    def test_import_result_includes_harvest_mapped(self):
        """Test that ImportResult schema includes harvest_mapped field."""
        from leave_bot.web.schemas import ImportResult

        result = ImportResult(
            imported=5,
            updated=3,
            skipped=2,
            harvest_mapped=4,
            errors=[],
        )

        assert result.imported == 5
        assert result.updated == 3
        assert result.skipped == 2
        assert result.harvest_mapped == 4
        assert result.errors == []

    def test_import_result_harvest_mapped_defaults_to_zero(self):
        """Test that harvest_mapped defaults to 0."""
        from leave_bot.web.schemas import ImportResult

        result = ImportResult(
            imported=5,
            updated=3,
            skipped=2,
            errors=[],
        )

        assert result.harvest_mapped == 0
