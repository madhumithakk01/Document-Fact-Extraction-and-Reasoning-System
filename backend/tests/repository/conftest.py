"""A recording async session so repository queries can be inspected without a DB."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import Select
from sqlalchemy.dialects import postgresql


class _Result:
    def scalars(self) -> _Result:
        return self

    def all(self) -> list:
        return []

    def scalar_one_or_none(self) -> None:
        return None

    def scalar_one(self) -> None:  # pragma: no cover - unused path
        return None

    def first(self) -> None:
        return None


class RecordingSession:
    """Captures every statement passed to ``execute`` and returns an empty result."""

    def __init__(self) -> None:
        self.statements: list[Any] = []

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> _Result:
        self.statements.append(statement)
        return _Result()

    async def get(self, *args: Any, **kwargs: Any) -> None:
        self.statements.append(("get", args))
        return None

    async def flush(self) -> None:  # pragma: no cover - trivial
        return None


@pytest.fixture
def session() -> RecordingSession:
    return RecordingSession()


def compiled_sql(statement: Select) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": False},
        )
    ).replace("\n", " ")
