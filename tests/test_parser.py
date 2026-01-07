"""Tests for LLM leave message parser."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from openai import OpenAIError

from leave_bot.bot.parser import (
    LeaveDate,
    ParsedLeave,
    parse_leave_message,
    validate_parsed_dates,
)


class TestParsedLeaveModel:
    """Tests for ParsedLeave Pydantic model."""

    def test_basic_leave_request(self):
        """Test creating a basic leave request."""
        parsed = ParsedLeave(
            is_leave_request=True,
            is_cancellation=False,
            confidence="high",
            dates=[LeaveDate(date="2026-01-05", type="full", category="vacation")],
            original_text_summary="Leave on January 5th",
            ambiguity_notes="",
        )

        assert parsed.is_leave_request is True
        assert len(parsed.dates) == 1
        assert parsed.dates[0].date == "2026-01-05"

    def test_sick_leave(self):
        """Test sick leave parsing."""
        parsed = ParsedLeave(
            is_leave_request=True,
            is_cancellation=False,
            confidence="high",
            dates=[LeaveDate(date="2026-01-05", type="full", category="sick")],
            original_text_summary="Sick leave",
            ambiguity_notes="",
        )

        assert parsed.dates[0].category == "sick"

    def test_half_day_leave(self):
        """Test half-day leave types."""
        parsed = ParsedLeave(
            is_leave_request=True,
            is_cancellation=False,
            confidence="high",
            dates=[
                LeaveDate(date="2026-01-05", type="half_am", category="vacation"),
                LeaveDate(date="2026-01-06", type="half_pm", category="vacation"),
            ],
            original_text_summary="Half-day leaves",
            ambiguity_notes="",
        )

        assert parsed.dates[0].type == "half_am"
        assert parsed.dates[1].type == "half_pm"

    def test_cancellation_request(self):
        """Test cancellation parsing."""
        parsed = ParsedLeave(
            is_leave_request=True,
            is_cancellation=True,
            confidence="high",
            dates=[LeaveDate(date="2026-01-05", type="full", category="vacation")],
            original_text_summary="Cancel leave",
            ambiguity_notes="",
        )

        assert parsed.is_cancellation is True


class TestValidateParsedDates:
    """Tests for date validation function."""

    def test_valid_future_date(self):
        """Test validation of future dates."""
        reference = date(2026, 1, 2)
        parsed = ParsedLeave(
            is_leave_request=True,
            is_cancellation=False,
            confidence="high",
            dates=[LeaveDate(date="2026-01-05", type="full", category="vacation")],
            original_text_summary="Future leave",
            ambiguity_notes="",
        )

        valid, warnings = validate_parsed_dates(parsed, reference)

        assert len(valid) == 1
        assert len(warnings) == 0

    def test_date_before_jan_1(self):
        """Test rejection of dates before Jan 1 of current year."""
        reference = date(2026, 1, 2)
        parsed = ParsedLeave(
            is_leave_request=True,
            is_cancellation=False,
            confidence="high",
            dates=[LeaveDate(date="2025-12-31", type="full", category="vacation")],
            original_text_summary="Old leave",
            ambiguity_notes="",
        )

        valid, warnings = validate_parsed_dates(parsed, reference)

        assert len(valid) == 0
        assert len(warnings) == 1
        assert "before Jan 1" in warnings[0]

    def test_invalid_date_format(self):
        """Test handling of invalid date formats."""
        reference = date(2026, 1, 2)
        parsed = ParsedLeave(
            is_leave_request=True,
            is_cancellation=False,
            confidence="high",
            dates=[LeaveDate(date="invalid-date", type="full", category="vacation")],
            original_text_summary="Bad date",
            ambiguity_notes="",
        )

        valid, warnings = validate_parsed_dates(parsed, reference)

        assert len(valid) == 0
        assert len(warnings) == 1
        assert "Invalid date format" in warnings[0]

    def test_mixed_valid_invalid(self):
        """Test mix of valid and invalid dates."""
        reference = date(2026, 1, 2)
        parsed = ParsedLeave(
            is_leave_request=True,
            is_cancellation=False,
            confidence="high",
            dates=[
                LeaveDate(date="2026-01-05", type="full", category="vacation"),
                LeaveDate(date="2025-12-20", type="full", category="vacation"),
                LeaveDate(date="2026-01-10", type="full", category="vacation"),
            ],
            original_text_summary="Multiple dates",
            ambiguity_notes="",
        )

        valid, warnings = validate_parsed_dates(parsed, reference)

        assert len(valid) == 2
        assert len(warnings) == 1


class TestParseLeaveMessage:
    """Tests for the main parse function."""

    @pytest.mark.asyncio
    async def test_parse_simple_leave(self, mock_openai_response):
        """Test parsing a simple leave message."""
        mock_parsed = ParsedLeave(
            is_leave_request=True,
            is_cancellation=False,
            confidence="high",
            dates=[LeaveDate(date="2026-01-05", type="full", category="vacation")],
            original_text_summary="Leave on the 5th",
            ambiguity_notes="",
        )

        with patch("leave_bot.bot.parser.OpenAI") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value = mock_instance
            mock_instance.responses.create.return_value = mock_openai_response(mock_parsed)

            result = await parse_leave_message(
                "I'll be on leave on the 5th",
                reference_date=date(2026, 1, 2),
            )

            assert result.is_leave_request is True
            assert len(result.dates) == 1

    @pytest.mark.asyncio
    async def test_parse_wfh_not_leave(self, mock_openai_response):
        """Test that WFH is not parsed as leave."""
        mock_parsed = ParsedLeave(
            is_leave_request=False,
            is_cancellation=False,
            confidence="high",
            dates=[],
            original_text_summary="Working from home",
            ambiguity_notes="",
        )

        with patch("leave_bot.bot.parser.OpenAI") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value = mock_instance
            mock_instance.responses.create.return_value = mock_openai_response(mock_parsed)

            result = await parse_leave_message(
                "WFH today",
                reference_date=date(2026, 1, 2),
            )

            assert result.is_leave_request is False

    @pytest.mark.asyncio
    async def test_parse_error_handling(self):
        """Test error handling when OpenAI fails."""
        with patch("leave_bot.bot.parser.OpenAI") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value = mock_instance
            mock_instance.responses.create.side_effect = OpenAIError("API Error")

            result = await parse_leave_message(
                "On leave tomorrow",
                reference_date=date(2026, 1, 2),
            )

            assert result.is_leave_request is False
            assert result.confidence == "low"


# Test cases from specification Appendix A
class TestSpecificationExamples:
    """Tests based on examples from the specification."""

    @pytest.mark.asyncio
    async def test_tomorrow_leave(self, mock_openai_response):
        """Test: 'On leave tomorrow'"""
        mock_parsed = ParsedLeave(
            is_leave_request=True,
            is_cancellation=False,
            confidence="high",
            dates=[LeaveDate(date="2026-01-03", type="full", category="vacation")],
            original_text_summary="Leave tomorrow",
            ambiguity_notes="",
        )

        with patch("leave_bot.bot.parser.OpenAI") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value = mock_instance
            mock_instance.responses.create.return_value = mock_openai_response(mock_parsed)

            result = await parse_leave_message(
                "On leave tomorrow",
                reference_date=date(2026, 1, 2),
            )

            assert result.is_leave_request is True
            assert result.confidence == "high"
            assert len(result.dates) == 1

    @pytest.mark.asyncio
    async def test_sick_leave_range(self, mock_openai_response):
        """Test: 'Taking sick leave 5th-7th'"""
        mock_parsed = ParsedLeave(
            is_leave_request=True,
            is_cancellation=False,
            confidence="high",
            dates=[
                LeaveDate(date="2026-01-05", type="full", category="sick"),
                LeaveDate(date="2026-01-06", type="full", category="sick"),
                LeaveDate(date="2026-01-07", type="full", category="sick"),
            ],
            original_text_summary="Sick leave 5th to 7th",
            ambiguity_notes="",
        )

        with patch("leave_bot.bot.parser.OpenAI") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value = mock_instance
            mock_instance.responses.create.return_value = mock_openai_response(mock_parsed)

            result = await parse_leave_message(
                "Taking sick leave 5th-7th",
                reference_date=date(2026, 1, 2),
            )

            assert result.is_leave_request is True
            assert len(result.dates) == 3
            assert all(d.category == "sick" for d in result.dates)

    @pytest.mark.asyncio
    async def test_half_day_afternoon(self, mock_openai_response):
        """Test: 'Half day tomorrow afternoon'"""
        mock_parsed = ParsedLeave(
            is_leave_request=True,
            is_cancellation=False,
            confidence="high",
            dates=[LeaveDate(date="2026-01-03", type="half_pm", category="vacation")],
            original_text_summary="Half day afternoon tomorrow",
            ambiguity_notes="",
        )

        with patch("leave_bot.bot.parser.OpenAI") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value = mock_instance
            mock_instance.responses.create.return_value = mock_openai_response(mock_parsed)

            result = await parse_leave_message(
                "Half day tomorrow afternoon",
                reference_date=date(2026, 1, 2),
            )

            assert result.is_leave_request is True
            assert result.dates[0].type == "half_pm"
