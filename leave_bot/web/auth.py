"""Google OAuth authentication for web dashboard."""

from functools import wraps
from pathlib import Path
from typing import Callable

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from leave_bot.config import get_settings
from leave_bot.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Initialize OAuth
oauth = OAuth()

# Templates for login page
templates_path = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_path))


def setup_oauth():
    """Configure Google OAuth client."""
    settings = get_settings()
    oauth.register(
        name="google",
        client_id=settings.google_oauth_client_id,
        client_secret=settings.google_oauth_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


@router.get("/login")
async def login(request: Request):
    """Show login page or redirect to Google OAuth."""
    # If already logged in, redirect to home
    user = request.session.get("user")
    if user:
        return RedirectResponse(url="/", status_code=302)

    # Show login page
    return templates.TemplateResponse("login.html", {"request": request})


@router.get("/google")
async def google_login(request: Request):
    """Initiate Google OAuth flow."""
    settings = get_settings()
    redirect_uri = settings.oauth_redirect_uri
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/callback")
async def callback(request: Request):
    """Handle OAuth callback from Google."""
    settings = get_settings()

    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as e:
        logger.error("oauth_callback_failed", error=str(e))
        raise HTTPException(status_code=401, detail="Authentication failed")

    user_info = token.get("userinfo")
    if not user_info:
        raise HTTPException(status_code=401, detail="Failed to get user info")

    email = user_info.get("email", "")
    allowed_domain = settings.allowed_email_domain

    # Verify email domain
    if not email.endswith(f"@{allowed_domain}"):
        logger.warning("oauth_domain_rejected", email=email, allowed_domain=allowed_domain)
        raise HTTPException(
            status_code=403,
            detail=f"Access restricted to @{allowed_domain} accounts",
        )

    # Store user info in session
    request.session["user"] = {
        "email": email,
        "name": user_info.get("name", email.split("@")[0]),
        "picture": user_info.get("picture"),
    }

    logger.info("user_logged_in", email=email)
    return RedirectResponse(url="/", status_code=302)


@router.get("/logout")
async def logout(request: Request):
    """Log out user and clear session."""
    user = request.session.get("user", {})
    email = user.get("email", "unknown")

    request.session.clear()
    logger.info("user_logged_out", email=email)

    return RedirectResponse(url="/auth/login", status_code=302)


def get_current_user(request: Request) -> dict | None:
    """Get current user from session."""
    return request.session.get("user")


def require_auth(request: Request) -> dict:
    """Dependency to require authentication."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def login_required(func: Callable) -> Callable:
    """Decorator to require login for route handlers."""

    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        user = get_current_user(request)
        if not user:
            return RedirectResponse(url="/auth/login", status_code=302)
        return await func(request, *args, **kwargs)

    return wrapper
