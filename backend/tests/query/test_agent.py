from __future__ import annotations

import json
import uuid

from app.providers.base import CompletionRequest, CompletionResult, LLMProvider, ProviderError
from app.query.agent import gather


class _Fact:
    def __init__(self, fid: uuid.UUID) -> None:
        self.fact_id = fid


class FakeTools:
    def __init__(self, facts_per_search: int = 2) -> None:
        self.facts_per_search = facts_per_search
        self.search_calls: list[str] = []
        self.rel_calls: list[uuid.UUID] = []

    async def search_facts(self, query: str, *, fact_kind=None):  # noqa: ANN001
        self.search_calls.append(query)
        return [_Fact(uuid.uuid4()) for _ in range(self.facts_per_search)]

    async def get_relationships(self, fact_id: uuid.UUID):
        self.rel_calls.append(fact_id)
        return []

    async def render_search(self, facts) -> str:  # noqa: ANN001
        return f"{len(facts)} facts"

    async def render_relationships(self, rels) -> str:  # noqa: ANN001
        return "(no relationships)"


class ScriptedProvider(LLMProvider):
    name = "scripted"

    def __init__(self, steps: list[object]) -> None:
        self.steps = list(steps)
        self.calls = 0

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        self.calls += 1
        item = self.steps.pop(0) if self.steps else {"action": "conclude", "rationale": "done"}
        if isinstance(item, Exception):
            raise item
        return CompletionResult(text=json.dumps(item), model="m", provider="scripted")

    async def health_check(self) -> bool:
        return True


def _search(q: str) -> dict:
    return {
        "action": "search_facts",
        "query": q,
        "fact_kind": None,
        "fact_id": None,
        "rationale": "look",
    }


def _rels(fid: str) -> dict:
    return {
        "action": "get_relationships",
        "query": None,
        "fact_kind": None,
        "fact_id": fid,
        "rationale": "check disputes",
    }


async def test_gathers_facts_across_searches_then_concludes() -> None:
    tools = FakeTools()
    provider = ScriptedProvider(
        [_search("EBITDA"), _search("revenue"), {"action": "conclude", "rationale": "enough"}]
    )
    ids, trace, used = await gather("q", tools, provider)

    assert tools.search_calls == ["EBITDA", "revenue"]
    assert len(ids) == 4  # 2 per search, all distinct
    assert used == 2
    assert [t.tool for t in trace] == ["search_facts", "search_facts", "conclude"]


async def test_respects_the_step_cap() -> None:
    tools = FakeTools()
    provider = ScriptedProvider([_search(f"q{i}") for i in range(10)])
    _ids, trace, used = await gather("q", tools, provider, max_steps=3)
    assert used == 3
    assert len(tools.search_calls) == 3


async def test_relationship_lookup_is_traced() -> None:
    fid = str(uuid.uuid4())
    tools = FakeTools()
    provider = ScriptedProvider(
        [_search("gdp"), _rels(fid), {"action": "conclude", "rationale": "done"}]
    )
    _ids, trace, _used = await gather("q", tools, provider)
    assert tools.rel_calls == [uuid.UUID(fid)]
    assert any(t.tool == "get_relationships" for t in trace)


async def test_invalid_fact_id_does_not_break_the_loop() -> None:
    tools = FakeTools()
    provider = ScriptedProvider(
        [_rels("not-a-uuid"), _search("recover"), {"action": "conclude", "rationale": "ok"}]
    )
    ids, trace, _used = await gather("q", tools, provider)
    assert tools.rel_calls == []
    assert len(ids) == 2  # the recovery search still ran
    assert any("invalid fact id" in t.result for t in trace)


async def test_planning_error_ends_gathering() -> None:
    tools = FakeTools()
    provider = ScriptedProvider([_search("gdp"), ProviderError("503")])
    ids, trace, used = await gather("q", tools, provider)
    assert used == 1
    assert trace[-1].tool == "error"
    assert len(ids) == 2
