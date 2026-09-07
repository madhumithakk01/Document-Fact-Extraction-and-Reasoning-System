from __future__ import annotations

import uuid

import pytest

from app.models.fact import Fact
from app.repository.scope import ProjectScope, scoped_select
from tests.repository.conftest import compiled_sql


def test_scope_requires_a_real_uuid() -> None:
    with pytest.raises(TypeError):
        ProjectScope(project_id="not-a-uuid", session=None)  # type: ignore[arg-type]


def test_scoped_select_pins_project_id_first() -> None:
    scope = ProjectScope(project_id=uuid.uuid4(), session=None)
    sql = compiled_sql(scoped_select(Fact, scope))
    assert "facts.project_id = " in sql
    assert sql.index("WHERE") < sql.index("facts.project_id = ")


def test_scoped_select_appends_extra_predicates_after_the_scope() -> None:
    scope = ProjectScope(project_id=uuid.uuid4(), session=None)
    sql = compiled_sql(scoped_select(Fact, scope, Fact.fact_kind == "quantitative"))
    assert "facts.project_id = " in sql
    assert "facts.fact_kind = " in sql


def test_scoped_select_rejects_models_without_project_id() -> None:
    scope = ProjectScope(project_id=uuid.uuid4(), session=None)

    class NotScoped:  # a model with no project boundary must not be queryable here
        pass

    with pytest.raises(TypeError, match="project_id"):
        scoped_select(NotScoped, scope)
