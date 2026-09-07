"""Database helpers for local development.

    python -m scripts.db upgrade      # run all migrations
    python -m scripts.db reset        # drop everything and re-migrate
    python -m scripts.db current      # show the current revision

Point DATABASE_URL at a Postgres 16 with the pgvector extension available
(``docker compose up -d db`` from the repo root brings one up).
"""

from __future__ import annotations

import subprocess
import sys

from sqlalchemy import text

from app.config import get_settings


def _alembic(*args: str) -> int:
    return subprocess.call([sys.executable, "-m", "alembic", *args])


async def _drop_all() -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(get_settings().database_url)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await engine.dispose()


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    command = argv[0]
    if command == "upgrade":
        return _alembic("upgrade", "head")
    if command == "current":
        return _alembic("current")
    if command == "downgrade":
        return _alembic("downgrade", argv[1] if len(argv) > 1 else "-1")
    if command == "reset":
        import asyncio

        asyncio.run(_drop_all())
        return _alembic("upgrade", "head")
    print(f"unknown command: {command}\n{__doc__}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
