"""Main entry point for the Leave Bot application."""

import asyncio

import typer
import uvicorn

from leave_bot.utils.logging import setup_logging

app = typer.Typer(
    name="leave-bot",
    help="Nilenso Leave Bot - Slack bot for leave management",
)


@app.command()
def bot(
    log_level: str = typer.Option("INFO", "--log-level", "-l", help="Log level"),
    json_logs: bool = typer.Option(False, "--json-logs", help="Output logs as JSON"),
) -> None:
    """Run the Slack bot with background worker."""
    setup_logging(level=log_level, json_format=json_logs)

    from leave_bot.bot.app import create_slack_app, start_socket_mode
    from leave_bot.bot.worker import start_worker
    from leave_bot.utils.logging import get_logger

    logger = get_logger(__name__)
    logger.info("starting_bot_mode")

    async def run():
        # Create Slack app
        slack_app = create_slack_app()

        # Start background worker
        worker = await start_worker()

        try:
            # Start Socket Mode
            await start_socket_mode(slack_app)
        except KeyboardInterrupt:
            logger.info("shutting_down")
            worker.stop()

    asyncio.run(run())


@app.command()
def web(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind to"),
    log_level: str = typer.Option("INFO", "--log-level", "-l", help="Log level"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload"),
) -> None:
    """Run the FastAPI web admin server."""
    setup_logging(level=log_level)

    from leave_bot.utils.logging import get_logger

    logger = get_logger(__name__)
    logger.info("starting_web_mode", host=host, port=port)

    uvicorn.run(
        "leave_bot.web.app:app",
        host=host,
        port=port,
        log_level=log_level.lower(),
        reload=reload,
    )


@app.command()
def worker(
    log_level: str = typer.Option("INFO", "--log-level", "-l", help="Log level"),
    json_logs: bool = typer.Option(False, "--json-logs", help="Output logs as JSON"),
) -> None:
    """Run only the background worker (for separate process)."""
    setup_logging(level=log_level, json_format=json_logs)

    from leave_bot.bot.worker import Worker
    from leave_bot.utils.logging import get_logger

    logger = get_logger(__name__)
    logger.info("starting_worker_mode")

    async def run():
        worker = Worker()
        try:
            await worker.run()
        except KeyboardInterrupt:
            logger.info("shutting_down")
            worker.stop()

    asyncio.run(run())


@app.command()
def migrate(
    revision: str = typer.Option("head", "--revision", "-r", help="Revision to migrate to"),
) -> None:
    """Run database migrations."""
    from alembic import command
    from alembic.config import Config

    from leave_bot.utils.logging import get_logger

    setup_logging()
    logger = get_logger(__name__)
    logger.info("running_migrations", revision=revision)

    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, revision)

    logger.info("migrations_complete")


@app.command()
def all(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Web host to bind to"),
    port: int = typer.Option(8000, "--port", "-p", help="Web port to bind to"),
    log_level: str = typer.Option("INFO", "--log-level", "-l", help="Log level"),
    json_logs: bool = typer.Option(False, "--json-logs", help="Output logs as JSON"),
) -> None:
    """Run bot, worker, and web server together."""
    setup_logging(level=log_level, json_format=json_logs)

    from leave_bot.bot.app import create_slack_app, start_socket_mode
    from leave_bot.bot.worker import start_worker
    from leave_bot.utils.logging import get_logger

    logger = get_logger(__name__)
    logger.info("starting_all_mode")

    async def run():
        # Create Slack app
        slack_app = create_slack_app()

        # Start background worker
        worker = await start_worker()

        # Start web server in background
        config = uvicorn.Config(
            "leave_bot.web.app:app",
            host=host,
            port=port,
            log_level=log_level.lower(),
        )
        server = uvicorn.Server(config)
        web_task = asyncio.create_task(server.serve())

        try:
            # Start Socket Mode (blocking)
            await start_socket_mode(slack_app)
        except KeyboardInterrupt:
            logger.info("shutting_down")
            worker.stop()
            server.should_exit = True
            await web_task

    asyncio.run(run())


if __name__ == "__main__":
    app()
