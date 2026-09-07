"""Operational health checks: process liveness, database reachability, and a
guarded trivial round-trip against the configured LLM provider."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_session
from app.providers import get_llm_provider
from app.providers.base import ProviderError

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    env: str
    llm_provider: str


class DependencyCheck(BaseModel):
    name: str
    ok: bool
    detail: str | None = None


class ReadinessResponse(BaseModel):
    ready: bool
    checks: list[DependencyCheck]


@router.get("/health", response_model=HealthResponse)
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        env=settings.app_env,
        llm_provider=settings.llm_provider.value,
    )


@router.get("/health/ready", response_model=ReadinessResponse)
async def readiness(session: AsyncSession = Depends(get_session)) -> ReadinessResponse:
    checks: list[DependencyCheck] = []

    try:
        await session.execute(text("SELECT 1"))
        checks.append(DependencyCheck(name="database", ok=True))
    except Exception as exc:  # noqa: BLE001 - surfaced verbatim in the response
        checks.append(DependencyCheck(name="database", ok=False, detail=str(exc)))

    try:
        vector_ok = (
            await session.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
        ).first() is not None
        checks.append(
            DependencyCheck(
                name="pgvector",
                ok=vector_ok,
                detail=None if vector_ok else "extension not installed; run migrations",
            )
        )
    except Exception as exc:  # noqa: BLE001
        checks.append(DependencyCheck(name="pgvector", ok=False, detail=str(exc)))

    try:
        provider = get_llm_provider()
        await provider.health_check()
        checks.append(DependencyCheck(name=f"llm:{provider.name}", ok=True))
    except ProviderError as exc:
        checks.append(DependencyCheck(name="llm", ok=False, detail=str(exc)))

    return ReadinessResponse(ready=all(c.ok for c in checks), checks=checks)
