"""Slack Bolt application setup."""

from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp

from leave_bot.bot.handlers import register_handlers
from leave_bot.config import get_settings
from leave_bot.utils.logging import get_logger

logger = get_logger(__name__)


def create_slack_app() -> AsyncApp:
    settings = get_settings()

    app = AsyncApp(
        token=settings.slack_bot_token,
        signing_secret=settings.slack_signing_secret,
    )

    # Register all handlers
    register_handlers(app)

    logger.info("slack_app_created")
    return app


async def start_socket_mode(app: AsyncApp) -> None:
    settings = get_settings()

    handler = AsyncSocketModeHandler(app, settings.slack_app_token)

    logger.info("starting_socket_mode")
    await handler.start_async()


async def check_slack_connection() -> bool:
    from slack_sdk.errors import SlackApiError
    from slack_sdk.web.async_client import AsyncWebClient

    settings = get_settings()

    try:
        client = AsyncWebClient(token=settings.slack_bot_token)
        response = await client.auth_test()

        if response["ok"]:
            logger.info(
                "slack_connection_healthy",
                team=response.get("team"),
                user=response.get("user"),
            )
            return True
        return False
    except SlackApiError as e:
        logger.error("slack_connection_failed", error=str(e))
        return False
