"""The hard-partition invariant: every repository read is bound to one project.

For each read helper we run it through a recording session, then assert the
statement it issued filters on ``<table>.project_id`` and that the SQL is
byte-identical for two different projects (only the bound value changes).
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy import Select

from app.repository import (
    ProjectScope,
    get_document,
    get_document_by_hash,
    get_fact,
    get_relationship,
    list_concepts,
    list_documents,
    list_facts,
    list_relationships,
)
from app.repository.facts import count_facts_by_status
from tests.repository.conftest import RecordingSession, compiled_sql

# (label, table, callable taking a ProjectScope)
_READS: list[tuple[str, str, Callable[[ProjectScope], Awaitable]]] = [
    ("list_documents", "documents", lambda s: list_documents(s)),
    ("get_document", "documents", lambda s: get_document(s, uuid.uuid4())),
    ("get_document_by_hash", "documents", lambda s: get_document_by_hash(s, "abc")),
    ("list_facts", "facts", lambda s: list_facts(s)),
    (
        "list_facts filtered",
        "facts",
        lambda s: list_facts(
            s, entity="Delhivery", fact_kind="quantitative", verification_status="verified"
        ),
    ),
    ("get_fact", "facts", lambda s: get_fact(s, uuid.uuid4())),
    ("count_facts_by_status", "facts", lambda s: count_facts_by_status(s)),
    ("list_relationships", "fact_relationships", lambda s: list_relationships(s)),
    (
        "list_relationships filtered",
        "fact_relationships",
        lambda s: list_relationships(s, relationship_type="contradicts", min_confidence=0.5),
    ),
    ("get_relationship", "fact_relationships", lambda s: get_relationship(s, uuid.uuid4())),
    ("list_concepts", "canonical_concepts", lambda s: list_concepts(s)),
]


async def _capture(build: Callable[[ProjectScope], Awaitable], project_id: uuid.UUID) -> Select:
    session = RecordingSession()
    await build(ProjectScope(project_id=project_id, session=session))
    stmts = [s for s in session.statements if isinstance(s, Select)]
    assert len(stmts) == 1, f"expected exactly one SELECT, got {len(stmts)}"
    return stmts[0]


@pytest.mark.parametrize(("label", "table", "build"), _READS, ids=[r[0] for r in _READS])
async def test_read_is_bound_to_the_scope_project(
    label: str, table: str, build: Callable[[ProjectScope], Awaitable]
) -> None:
    stmt = await _capture(build, uuid.uuid4())
    sql = compiled_sql(stmt)
    assert re.search(rf"\b{table}\.project_id = ", sql), f"{label}: not scoped -> {sql}"


@pytest.mark.parametrize(("label", "table", "build"), _READS, ids=[r[0] for r in _READS])
async def test_only_the_bound_project_value_changes_between_projects(
    label: str, table: str, build: Callable[[ProjectScope], Awaitable]
) -> None:
    a = await _capture(build, uuid.uuid4())
    b = await _capture(build, uuid.uuid4())
    # compiled SQL (with names, not literals) must be identical: the project id
    # is a bound parameter, never inlined, so nothing structural differs.
    assert compiled_sql(a) == compiled_sql(b)


async def test_no_read_helper_emits_an_unscoped_select() -> None:
    for _label, table, build in _READS:
        stmt = await _capture(build, uuid.uuid4())
        sql = compiled_sql(stmt)
        # the very first predicate after WHERE is the project bound
        where = sql.split(" WHERE ", 1)[1]
        assert where.lstrip().startswith(f"{table}.project_id = ")
