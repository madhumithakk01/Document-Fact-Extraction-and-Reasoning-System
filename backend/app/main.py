"""FastAPI application entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api import health_router
from app.config import get_settings
from app.db import engine
from app.logging_config import configure_logging
from app.providers.factory import get_llm_provider


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    yield
    provider = get_llm_provider()
    await provider.aclose()
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(
        title="Fact knowledge layer",
        version=__version__,
        lifespan=lifespan,
    )
    app.include_router(health_router)
    return app


app = create_app()
