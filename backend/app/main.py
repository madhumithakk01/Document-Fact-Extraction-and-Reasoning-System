"""FastAPI application entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api import ALL_ROUTERS
from app.config import get_settings
from app.db import engine
from app.logging_config import configure_logging
from app.providers.factory import get_llm_provider

PAGE_IMAGE_MOUNT = "/media/page-images"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    yield
    try:
        provider = get_llm_provider()
        await provider.aclose()
    except Exception:  # noqa: BLE001 - best-effort shutdown
        pass
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Fact knowledge layer",
        version=__version__,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for router in ALL_ROUTERS:
        app.include_router(router)

    image_dir = Path(settings.page_image_dir)
    image_dir.mkdir(parents=True, exist_ok=True)
    app.mount(PAGE_IMAGE_MOUNT, StaticFiles(directory=image_dir), name="page-images")

    return app


app = create_app()
