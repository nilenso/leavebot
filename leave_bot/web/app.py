"""FastAPI application setup."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from leave_bot.utils.logging import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("web_app_starting")
    yield
    logger.info("web_app_stopping")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Nilenso Leave Bot Admin",
        description="Admin interface for the Leave Bot",
        version="0.1.0",
        lifespan=lifespan,
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

    from leave_bot.web.routes import config, health, leaves, users

    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(users.router, prefix="/api", tags=["users"])
    app.include_router(leaves.router, prefix="/api", tags=["leaves"])
    app.include_router(config.router, prefix="/api", tags=["config"])

    templates_path = Path(__file__).parent / "templates"
    templates = Jinja2Templates(directory=str(templates_path))

    @app.get("/", include_in_schema=False)
    async def dashboard(request: Request):
        return templates.TemplateResponse("dashboard.html", {"request": request})

    @app.get("/users", include_in_schema=False)
    async def users_page(request: Request):
        return templates.TemplateResponse("users.html", {"request": request})

    @app.get("/leaves", include_in_schema=False)
    async def leaves_page(request: Request):
        return templates.TemplateResponse("leaves.html", {"request": request})

    @app.get("/config", include_in_schema=False)
    async def config_page(request: Request):
        return templates.TemplateResponse("config.html", {"request": request})

    logger.info("web_app_created")
    return app


# Create app instance for uvicorn
app = create_app()
