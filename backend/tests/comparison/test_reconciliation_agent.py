from __future__ import annotations

import json

from app.comparison.adjudicator import Adjudication, RelationshipType
from app.comparison.precheck import ComparableFact
from app.comparison.reconciliation_agent import reconcile
from app.providers.base import CompletionRequest, CompletionResult, LLMProvider, ProviderError

_A = ComparableFact(
    "quantitative",
    "India",
    "real GDP growth",
    {"comparator": "eq", "number": 6.5, "unit": "%"},
    {"raw_label": "2025-26"},
)
_B = ComparableFact(
    "quantitative",
    "India",
    "real GDP growth",
    {"comparator": "eq", "number": 6.6, "unit": "%"},
    {"raw_label": "2025-26"},
)

_INITIAL = Adjudication(
    relationship_type=RelationshipType.contradicts,
    reconciliation_basis=None,
    explanation="values differ",
    confidence=0.4,
    needs_more_context=True,
    missing_context="check whether the IMF figure is on a different vintage",
    reasoning={},
)


class ScriptedProvider(LLMProvider):
    """Answers planning steps from ``steps`` in order; every other call (the
    forced final adjudication) returns ``final``."""

    name = "scripted"

    def __init__(self, steps: list[object], final: dict) -> None:
        self.steps = list(steps)
        self.final = final
        self.step_calls = 0
        self.final_calls = 0

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        if "next step" in request.user.lower() or "FINDINGS SO FAR" in request.user:
            self.step_calls += 1
            item = self.steps.pop(0) if self.steps else {"action": "finish", "rationale": "done"}
            if isinstance(item, Exception):
                raise item
            return CompletionResult(text=json.dumps(item), model="m", provider="scripted")
        self.final_calls += 1
        return CompletionResult(text=json.dumps(self.final), model="m", provider="scripted")

    async def health_check(self) -> bool:
        return True


class FakeTools:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def call(self, tool: str, *, query=None, fact_id=None) -> str:
        self.calls.append((tool, {"query": query, "fact_id": fact_id}))
        return f"{tool} result for {query or fact_id}"


def _step(tool: str, query: str = "x") -> dict:
    return {
        "action": "use_tool",
        "tool": tool,
        "query": query,
        "fact_id": None,
        "rationale": "look",
    }


def _final(rt: str, basis: str | None = None) -> dict:
    return {
        "entity_match": True,
        "attribute_match": True,
        "period_relation": "same",
        "unit_scale_note": "",
        "qualifier_explanation": "",
        "comparator_consistent": True,
        "relationship_type": rt,
        "reconciliation_basis": basis,
        "explanation": "final call",
        "confidence": 0.7,
        "needs_more_context": False,
        "missing_context": None,
    }


async def test_uses_up_to_three_tools_then_forces_a_verdict() -> None:
    provider = ScriptedProvider(
        [_step("search_facts"), _step("search_evidence_text"), _step("get_surrounding_context")],
        _final("contradicts"),
    )
    tools = FakeTools()
    result = await reconcile(_A, "e1", _B, "e2", _INITIAL, tools, provider)

    assert len(tools.calls) == 3
    assert result.tool_calls_used == 3
    assert result.budget_exhausted is True
    assert result.adjudication.relationship_type is RelationshipType.contradicts
    tool_entries = [e for e in result.trail if e.get("tool")]
    assert [e["tool"] for e in tool_entries] == [
        "search_facts",
        "search_evidence_text",
        "get_surrounding_context",
    ]
    assert result.trail[-1]["action"] == "final_classification"
    assert provider.final_calls == 1


async def test_every_tool_call_is_logged_with_args_and_result() -> None:
    provider = ScriptedProvider(
        [_step("search_facts", "EBITDA basis")], _final("reconciled_by_context", "rounding")
    )
    result = await reconcile(_A, "e1", _B, "e2", _INITIAL, FakeTools(), provider)
    entry = next(e for e in result.trail if e.get("tool") == "search_facts")
    assert entry["args"]["query"] == "EBITDA basis"
    assert "search_facts result" in entry["result"]
    assert result.adjudication.reconciliation_basis == "rounding"


async def test_agent_can_finish_early() -> None:
    provider = ScriptedProvider(
        [_step("search_facts"), {"action": "finish", "rationale": "enough"}], _final("corroborates")
    )
    tools = FakeTools()
    result = await reconcile(_A, "e1", _B, "e2", _INITIAL, tools, provider)
    assert len(tools.calls) == 1
    assert result.budget_exhausted is False
    assert result.adjudication.relationship_type is RelationshipType.corroborates


async def test_planning_error_still_forces_a_final_classification() -> None:
    provider = ScriptedProvider([ProviderError("503")], _final("contradicts"))
    result = await reconcile(_A, "e1", _B, "e2", _INITIAL, FakeTools(), provider)
    assert any("error" in e for e in result.trail)
    assert result.trail[-1]["action"] == "final_classification"
    assert result.adjudication.relationship_type is RelationshipType.contradicts


async def test_invalid_tool_name_is_recorded_and_stops_the_loop() -> None:
    provider = ScriptedProvider(
        [
            {
                "action": "use_tool",
                "tool": "delete_everything",
                "query": "x",
                "fact_id": None,
                "rationale": "nope",
            }
        ],
        _final("unrelated"),
    )
    tools = FakeTools()
    result = await reconcile(_A, "e1", _B, "e2", _INITIAL, tools, provider)
    assert tools.calls == []
    assert any("invalid tool" in str(e.get("error", "")) for e in result.trail)
    assert result.trail[-1]["action"] == "final_classification"
