"""Tests for Slack message and action handlers."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from leave_bot.bot.handlers import has_trigger_keyword


class TestTriggerKeywords:
    """Tests for trigger keyword detection."""

    def test_has_leave_keyword(self):
        """Test detection of 'leave' keyword."""
        assert has_trigger_keyword("I'm on leave tomorrow", ["leave", "ooo"]) is True

    def test_has_ooo_keyword(self):
        """Test detection of 'ooo' keyword."""
        assert has_trigger_keyword("OOO next week", ["leave", "ooo"]) is True

    def test_has_sick_keyword(self):
        """Test detection of 'sick' keyword."""
        assert has_trigger_keyword("Sick today", ["sick", "vacation"]) is True

    def test_no_keyword(self):
        """Test message without keywords."""
        assert has_trigger_keyword("Working from office", ["leave", "ooo"]) is False

    def test_case_insensitive(self):
        """Test case-insensitive matching."""
        assert has_trigger_keyword("LEAVE tomorrow", ["leave"]) is True
        assert has_trigger_keyword("Leave Tomorrow", ["leave"]) is True

    def test_partial_match(self):
        """Test partial word matching - substring within word."""
        # 'leave' is NOT a substring of 'leaving' (leave vs leavi)
        assert has_trigger_keyword("Leaving early today", ["leave"]) is False
        # But 'ooo' is a substring of 'oooo'
        assert has_trigger_keyword("I said oooo", ["ooo"]) is True

    def test_empty_keywords(self):
        """Test with empty keywords list."""
        assert has_trigger_keyword("On leave", []) is False

    def test_empty_message(self):
        """Test with empty message."""
        assert has_trigger_keyword("", ["leave"]) is False


class TestMessageHandler:
    """Tests for the message handler."""

    @pytest.fixture
    def mock_event(self):
        """Create a mock Slack message event."""
        return {
            "type": "message",
            "channel": "C12345678",
            "user": "U12345678",
            "text": "I'll be on leave tomorrow",
            "ts": "1234567890.123456",
            "event_ts": "1234567890.123456",
        }

    @pytest.fixture
    def mock_say(self):
        """Create a mock say function."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_ignores_wrong_channel(self, mock_event, mock_say, mock_slack_client):
        """Test that messages from wrong channel are ignored."""
        from leave_bot.bot.handlers import handle_message

        mock_event["channel"] = "WRONG_CHANNEL"

        with patch("leave_bot.bot.handlers.get_settings") as mock_settings:
            mock_settings.return_value.slack_channel_id = "C12345678"
            mock_settings.return_value.trigger_keywords_list = ["leave"]

            await handle_message(mock_event, mock_say, mock_slack_client)

            mock_say.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_bot_messages(self, mock_event, mock_say, mock_slack_client):
        """Test that bot messages are ignored."""
        from leave_bot.bot.handlers import handle_message

        mock_event["bot_id"] = "B12345678"

        with patch("leave_bot.bot.handlers.get_settings") as mock_settings:
            mock_settings.return_value.slack_channel_id = "C12345678"
            mock_settings.return_value.trigger_keywords_list = ["leave"]

            await handle_message(mock_event, mock_say, mock_slack_client)

            mock_say.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_no_keywords(self, mock_event, mock_say, mock_slack_client):
        """Test that messages without keywords are ignored."""
        from leave_bot.bot.handlers import handle_message

        mock_event["text"] = "Hello everyone"

        with patch("leave_bot.bot.handlers.get_settings") as mock_settings:
            mock_settings.return_value.slack_channel_id = "C12345678"
            mock_settings.return_value.trigger_keywords_list = ["leave", "ooo"]

            await handle_message(mock_event, mock_say, mock_slack_client)

            mock_say.assert_not_called()


class TestButtonHandlers:
    """Tests for button action handlers."""

    @pytest.fixture
    def mock_confirm_body(self):
        """Create a mock button action body for confirmation."""
        return {
            "type": "block_actions",
            "user": {"id": "U12345678"},
            "channel": {"id": "C12345678"},
            "message": {"ts": "1234567890.123456"},
            "actions": [
                {
                    "action_id": "leave_confirm_abc12345",
                    "value": "abc12345-1234-1234-1234-123456789012",
                }
            ],
        }

    @pytest.fixture
    def mock_cancel_body(self):
        """Create a mock button action body for cancellation."""
        return {
            "type": "block_actions",
            "user": {"id": "U12345678"},
            "channel": {"id": "C12345678"},
            "message": {"ts": "1234567890.123456"},
            "actions": [
                {
                    "action_id": "leave_cancel_abc12345",
                    "value": "abc12345-1234-1234-1234-123456789012",
                }
            ],
        }

    @pytest.mark.asyncio
    async def test_cancel_updates_message(self, mock_cancel_body, mock_slack_client):
        """Test that cancel button updates the Slack message."""
        from contextlib import asynccontextmanager
        from leave_bot.bot.handlers import handle_leave_cancel

        mock_ack = AsyncMock()

        # Create a proper async context manager mock for get_session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # No pending action found
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        @asynccontextmanager
        async def mock_get_session():
            yield mock_session

        with patch("leave_bot.bot.handlers.get_session", mock_get_session):
            await handle_leave_cancel(mock_ack, mock_cancel_body, mock_slack_client)

        mock_ack.assert_called_once()
        mock_slack_client.chat_update.assert_called_once()


class TestBlockBuilders:
    """Tests for Block Kit message builders."""

    def test_confirmation_message_structure(self):
        """Test confirmation message has correct structure."""
        from leave_bot.bot.blocks import build_confirmation_message
        from leave_bot.bot.parser import LeaveDate, ParsedLeave

        parsed = ParsedLeave(
            is_leave_request=True,
            is_cancellation=False,
            confidence="high",
            dates=[LeaveDate(date="2026-01-05", type="full", category="vacation")],
            original_text_summary="Leave on the 5th",
            ambiguity_notes="",
        )

        blocks = build_confirmation_message(parsed, "test-action-id")

        # Should have header, summary, dates, confidence, divider, and actions
        assert len(blocks) >= 5
        assert blocks[0]["type"] == "header"
        assert blocks[-1]["type"] == "actions"

    def test_confirmation_message_with_conflicts(self):
        """Test confirmation message shows conflicts."""
        from leave_bot.bot.blocks import build_confirmation_message
        from leave_bot.bot.parser import LeaveDate, ParsedLeave

        parsed = ParsedLeave(
            is_leave_request=True,
            is_cancellation=False,
            confidence="high",
            dates=[LeaveDate(date="2026-01-05", type="full", category="vacation")],
            original_text_summary="Leave on the 5th",
            ambiguity_notes="",
        )

        blocks = build_confirmation_message(
            parsed,
            "test-action-id",
            has_conflicts=True,
            conflicting_dates=[date(2026, 1, 5)],
        )

        # Should contain conflict warning
        text_content = str(blocks)
        assert "CONFLICT" in text_content or "conflict" in text_content.lower()

    def test_success_message(self):
        """Test success message structure."""
        from leave_bot.bot.blocks import build_success_message
        from leave_bot.models.leave import LeaveRecord, LeaveStatus, LeaveType, LeaveCategory

        record = LeaveRecord(
            id=1,
            user_id=1,
            date=date(2026, 1, 5),
            leave_type=LeaveType.full,
            leave_category=LeaveCategory.vacation,
            status=LeaveStatus.completed,
        )

        blocks = build_success_message([record])

        assert len(blocks) >= 2
        assert "Confirmed" in str(blocks) or "confirmed" in str(blocks).lower()
        # Should mention both Calendar and Harvest when not skipped
        assert "Calendar and Harvest" in str(blocks)

    def test_success_message_harvest_skipped(self):
        """Test success message shows warning when Harvest is skipped."""
        from leave_bot.bot.blocks import build_success_message
        from leave_bot.models.leave import LeaveRecord, LeaveStatus, LeaveType, LeaveCategory

        record = LeaveRecord(
            id=1,
            user_id=1,
            date=date(2026, 1, 5),
            leave_type=LeaveType.full,
            leave_category=LeaveCategory.vacation,
            status=LeaveStatus.completed,
        )

        blocks = build_success_message([record], harvest_skipped=True)

        blocks_str = str(blocks)
        # Should NOT mention "Calendar and Harvest" together
        assert "Calendar and Harvest" not in blocks_str
        # Should mention only Calendar
        assert "Calendar" in blocks_str
        # Should show warning about Harvest being skipped
        assert "Harvest sync skipped" in blocks_str
        assert "no Harvest ID" in blocks_str

    def test_success_message_cancellation_harvest_skipped(self):
        """Test cancellation success message shows warning when Harvest is skipped."""
        from leave_bot.bot.blocks import build_success_message
        from leave_bot.models.leave import LeaveRecord, LeaveStatus, LeaveType, LeaveCategory

        record = LeaveRecord(
            id=1,
            user_id=1,
            date=date(2026, 1, 5),
            leave_type=LeaveType.full,
            leave_category=LeaveCategory.vacation,
            status=LeaveStatus.cancelled,
        )

        blocks = build_success_message([record], is_cancellation=True, harvest_skipped=True)

        blocks_str = str(blocks)
        # Should mention cancellation
        assert "Cancelled" in blocks_str
        # Should NOT mention "Calendar and Harvest" together
        assert "Calendar and Harvest" not in blocks_str
        # Should show warning about Harvest being skipped
        assert "Harvest sync skipped" in blocks_str

    def test_error_message(self):
        """Test error message structure."""
        from leave_bot.bot.blocks import build_error_message

        blocks = build_error_message("Something went wrong")

        assert len(blocks) >= 2
        assert "Error" in str(blocks) or "error" in str(blocks).lower()

    def test_expired_message(self):
        """Test expired message structure."""
        from leave_bot.bot.blocks import build_expired_message

        blocks = build_expired_message()

        assert len(blocks) >= 1
        assert "expired" in str(blocks).lower()
