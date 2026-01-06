"""FastAPI application setup."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from leave_bot.config import get_settings
from leave_bot.utils.logging import get_logger
from leave_bot.web.auth import get_current_user, router as auth_router, setup_oauth

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("web_app_starting")
    setup_oauth()
    yield
    logger.info("web_app_stopping")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Nilenso Leave Bot Admin",
        description="Admin interface for the Leave Bot",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Session middleware for OAuth (must be added before routes)
    app.add_middleware(
        SessionMiddleware,  # type: ignore[arg-type]
        secret_key=settings.session_secret_key,
        session_cookie="leave_bot_session",
        max_age=86400 * 7,  # 7 days
        same_site="lax",
        https_only=False,  # Set to True in production with HTTPS
    )

    app.add_middleware(
        CORSMiddleware,  # type: ignore[arg-type]
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error("unhandled_exception", error=str(exc), path=request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    # Include auth routes (public)
    app.include_router(auth_router)

    from leave_bot.web.routes import config, health, leaves, users

    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(users.router, prefix="/api", tags=["users"])
    app.include_router(leaves.router, prefix="/api", tags=["leaves"])
    app.include_router(config.router, prefix="/api", tags=["config"])

    templates_path = Path(__file__).parent / "templates"
    templates = Jinja2Templates(directory=str(templates_path))

    def render_protected(request: Request, template_name: str, context: dict | None = None):
        """Render template if authenticated, redirect to login otherwise."""
        user = get_current_user(request)
        if not user:
            return RedirectResponse(url="/auth/login", status_code=302)

        ctx = {"request": request, "user": user}
        if context:
            ctx.update(context)
        return templates.TemplateResponse(template_name, ctx)

    @app.get("/", include_in_schema=False)
    async def dashboard(request: Request):
        return render_protected(request, "dashboard.html")

    @app.get("/users", include_in_schema=False)
    async def users_page(request: Request):
        return render_protected(request, "users.html")

    @app.get("/leaves", include_in_schema=False)
    async def leaves_page(request: Request):
        return render_protected(request, "leaves.html")

    @app.get("/config", include_in_schema=False)
    async def config_page(request: Request):
        return render_protected(request, "config.html")

    logger.info("web_app_created")
    return app


# Create app instance for uvicorn
app = create_app()
