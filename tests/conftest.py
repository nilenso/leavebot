"""Test fixtures and configuration."""

import os

# Set test environment variables BEFORE importing anything that uses Settings
os.environ["SLACK_BOT_TOKEN"] = "xoxb-test-token"
os.environ["SLACK_APP_TOKEN"] = "xapp-test-token"
os.environ["SLACK_SIGNING_SECRET"] = "test-signing-secret"
os.environ["SLACK_CHANNEL_ID"] = "C12345678"
os.environ["OPENAI_API_KEY"] = "sk-test-key"
os.environ["GOOGLE_SERVICE_ACCOUNT_JSON_BASE64"] = (
    "eyJ0eXBlIjogInNlcnZpY2VfYWNjb3VudCJ9"  # {"type": "service_account"}
)
os.environ["GOOGLE_CALENDAR_ID"] = "test@calendar.google.com"
os.environ["HARVEST_ACCESS_TOKEN"] = "test-harvest-token"
os.environ["HARVEST_ACCOUNT_ID"] = "123456"
os.environ["HARVEST_PROJECT_ID"] = "789"
os.environ["HARVEST_VACATION_TASK_ID"] = "111"
os.environ["HARVEST_SICK_TASK_ID"] = "222"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

# Clear the settings cache to ensure test settings are used
from leave_bot.config import get_settings  # noqa: E402

get_settings.cache_clear()

import asyncio  # noqa: E402
from datetime import date, datetime  # noqa: E402
from typing import AsyncGenerator  # noqa: E402
from unittest.mock import AsyncMock, MagicMock  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker  # noqa: E402

from leave_bot.database import Base  # noqa: E402
from leave_bot.models.leave import LeaveCategory, LeaveRecord, LeaveStatus, LeaveType  # noqa: E402
from leave_bot.models.user import User  # noqa: E402


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create an in-memory SQLite database session for testing."""
    # Use SQLite for tests (simpler than testcontainers)
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def sample_user() -> User:
    """Create a sample user for testing."""
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
def sample_leave_record(sample_user: User) -> LeaveRecord:
    """Create a sample leave record for testing."""
    return LeaveRecord(
        id=1,
        user_id=sample_user.id,
        date=date(2026, 1, 5),
        leave_type=LeaveType.FULL,
        leave_category=LeaveCategory.VACATION,
        status=LeaveStatus.PENDING,
    )


@pytest.fixture
def mock_slack_client() -> MagicMock:
    """Create a mock Slack client."""
    client = MagicMock()
    client.chat_postMessage = AsyncMock(return_value={"ok": True, "ts": "1234567890.123456"})
    client.chat_update = AsyncMock(return_value={"ok": True})
    client.conversations_replies = AsyncMock(return_value={"ok": True, "messages": []})
    client.auth_test = AsyncMock(return_value={"ok": True, "team": "test", "user": "bot"})
    return client


@pytest.fixture
def mock_openai_response():
    """Create a mock OpenAI response factory."""

    def _create_response(parsed_data):
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.parsed = parsed_data
        return response

    return _create_response


@pytest.fixture
def current_date() -> date:
    """Get a fixed current date for testing."""
    return date(2026, 1, 2)


@pytest.fixture
def current_datetime(current_date: date) -> datetime:
    """Get a fixed current datetime for testing."""
    return datetime.combine(current_date, datetime.min.time(), tzinfo=ZoneInfo("Asia/Kolkata"))
