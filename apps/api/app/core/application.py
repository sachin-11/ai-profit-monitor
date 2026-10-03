from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import router
from app.core.config import Settings, get_settings
from app.core.errors import ApiError, api_error_handler, validation_error_handler
from app.core.ingestion_limits import IngestionBodyLimitMiddleware
from app.core.logging import configure_logging
from app.core.security import InMemoryLoginRateLimiter
from app.db.session import dispose_database


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await dispose_database()

    application = FastAPI(
        title=app_settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.settings = app_settings
    application.state.login_rate_limiter = InMemoryLoginRateLimiter(
        app_settings.login_rate_limit_attempts,
        app_settings.login_rate_limit_window_seconds,
    )
    application.add_exception_handler(ApiError, api_error_handler)
    application.add_exception_handler(RequestValidationError, validation_error_handler)
    application.add_middleware(
        IngestionBodyLimitMiddleware, max_body_bytes=app_settings.ingestion_max_body_bytes
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin).rstrip("/") for origin in app_settings.cors_origins],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["*"],
    )
    application.include_router(router)
    return application
