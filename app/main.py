"""FastAPI application factory and error translation."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import get_settings
from app.core.errors import DomainError
from app.routers import admin, auth, claims, health, items, locations, notifications

logger = logging.getLogger(__name__)


class RevalidatingStaticFiles(StaticFiles):
    """Serve the UI with a mandatory revalidation.

    StaticFiles sends ETag and Last-Modified but no Cache-Control, so browsers
    fall back to *heuristic* freshness and can keep running a stale script for
    a while after a deploy -- long enough for a shipped fix to look like it did
    nothing. `no-cache` does not mean "do not cache": it means "ask first", and
    the ETag answers that with a cheap 304 whenever the file has not changed.
    """

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers.setdefault("Cache-Control", "no-cache")
        return response


class ErrorResponse(BaseModel):
    """Typed error envelope, so even failures are a declared schema."""

    detail: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.run_migrations_on_startup:
        from app.db.migrations import run_migrations

        run_migrations()
    yield


def _configure_logging() -> None:
    """Make application logs visible.

    uvicorn configures its own loggers but leaves ours silent, which would hide
    mail delivery outcomes -- exactly the events an operator needs to see.
    """
    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.INFO)
    if not app_logger.handlers and not logging.getLogger().handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s [%(name)s] %(message)s"))
        app_logger.addHandler(handler)


def create_app() -> FastAPI:
    _configure_logging()
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description=(
            "Campus lost & found service. Items move through the lifecycle "
            "reported -> matched -> claimed -> closed."
        ),
        lifespan=lifespan,
        responses={
            400: {"model": ErrorResponse},
            401: {"model": ErrorResponse},
            403: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
        },
    )

    @application.exception_handler(DomainError)
    async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(detail=exc.detail).model_dump(),
        )

    for module in (health, auth, items, claims, locations, notifications, admin):
        application.include_router(module.router)

    # Browser UI, served same-origin under /app/ so there is no CORS to configure
    # and no possibility of colliding with an API path (no route starts with
    # /app). Purely additive: mounting does not alter any existing route.
    frontend_dir = Path(__file__).resolve().parents[1] / "frontend"
    if frontend_dir.is_dir():
        application.mount(
            "/app",
            RevalidatingStaticFiles(directory=str(frontend_dir), html=True),
            name="frontend",
        )
    else:  # pragma: no cover - the API is fully usable without the UI
        logger.warning("frontend/ not found at %s; UI not mounted", frontend_dir)

    return application


app = create_app()
