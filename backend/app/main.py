"""FastAPI application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.admin import router as admin_router
from app.api.v1.astrologer import router as astrologer_router
from app.api.v1.auth import router as auth_router
from app.core.config import Settings, get_settings
from app.core.security import validate_fernet_key


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory configuring routers, middleware, and lifespan checks."""
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        # Startup validation: App MUST refuse to start without valid secrets/keys
        if not app_settings.JWT_SECRET or len(app_settings.JWT_SECRET.strip()) < 32:
            raise RuntimeError(
                "Application refused to start: JWT_SECRET must be at least 32 characters"
            )
        try:
            validate_fernet_key(app_settings.ENCRYPTION_KEY)
        except ValueError:
            raise RuntimeError(
                "Application refused to start: ENCRYPTION_KEY must be a valid Fernet key"
            ) from None
        yield

    app = FastAPI(
        title="Kundali API",
        version="0.1.0",
        description="Deterministic Vedic astrology calculation and grounded platform backend",
        lifespan=lifespan,
    )

    # CORS middleware configuration
    if app_settings.CORS_ALLOWED_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=app_settings.CORS_ALLOWED_ORIGINS,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Mount API v1 router
    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(auth_router)
    api_v1.include_router(admin_router)
    api_v1.include_router(astrologer_router)
    app.include_router(api_v1)

    @app.get("/health", tags=["system"])
    def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "ok"}

    return app


# Default app instance (lazily initialized or created if env permits)
app: FastAPI | None = None
try:
    app = create_app()
except Exception:
    # Allows importing create_app without requiring active environment variables
    pass
