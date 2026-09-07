"""Bounded reconciliation agent (§6.5).

Runs only when adjudication asked for more context. It may make at most three
tool calls; every call and its result is appended to the investigation trail.
When the budget is spent (or the agent stops early) a final classification is
forced with whatever was found -- exhausting the budget without resolving the
disagreement is itself a valid, reportable outcome.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.comparison.adjudicator import Adjudication, adjudicate_pair
from app.comparison.precheck import ComparableFact
from app.comparison.tools import TOOL_NAMES, AgentTools
from app.providers.base import CompletionRequest, LLMProvider, ProviderError

logger = logging.getLogger(__name__)

MAX_TOOL_CALLS = 3

_STEP_SYSTEM = """\
You are resolving whether two facts corroborate, contradict, or are reconciled
by some context. Adjudication was uncertain and asked for a targeted lookup.

You have these read-only tools, all scoped to the project:
- search_facts(query): find other facts by entity / attribute / evidence text.
- search_evidence_text(query): find raw passages in the source documents.
- get_surrounding_context(fact_id): the full page text a fact came from.

Each step, either request ONE tool call that could change the verdict, or finish
if you have enough. You get at most three tool calls total.\
"""

_STEP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "action": {"type": "string", "enum": ["use_tool", "finish"]},
        "tool": {"type": ["string", "null"], "enum": [*TOOL_NAMES, None]},
        "query": {"type": ["string", "null"]},
        "fact_id": {"type": ["string", "null"]},
        "rationale": {"type": "string"},
    },
    "required": ["action", "tool", "query", "fact_id", "rationale"],
}


@dataclass(slots=True)
class ReconciliationResult:
    adjudication: Adjudication
    trail: list[dict[str, Any]] = field(default_factory=list)
    tool_calls_used: int = 0
    budget_exhausted: bool = False


async def reconcile(
    a: ComparableFact,
    evidence_a: str,
    b: ComparableFact,
    evidence_b: str,
    initial: Adjudication,
    tools: AgentTools,
    provider: LLMProvider,
    *,
    max_tool_calls: int = MAX_TOOL_CALLS,
) -> ReconciliationResult:
    trail: list[dict[str, Any]] = []
    findings: list[str] = []

    def _facts_block() -> str:
        from app.comparison.adjudicator import build_prompt

        return build_prompt(a, evidence_a, b, evidence_b)

    for step in range(1, max_tool_calls + 1):
        history = "\n\n".join(findings) if findings else "(nothing gathered yet)"
        user = (
            f"{_facts_block()}\n\n"
            f"ADJUDICATION SO FAR: {initial.relationship_type.value} "
            f"(needs more context: {initial.missing_context or 'unspecified'})\n\n"
            f"FINDINGS SO FAR ({step - 1}/{max_tool_calls} tool calls used):\n{history}\n\n"
            f"Decide the next step."
        )
        try:
            result = await provider.complete(
                CompletionRequest(
                    system=_STEP_SYSTEM, user=user, json_schema=_STEP_SCHEMA, temperature=0.0
                )
            )
            decision = result.json()
        except (ProviderError, ValueError) as exc:
            logger.warning("reconciliation planning step failed: %s", exc)
            trail.append({"step": step, "error": str(exc)[:200]})
            break

        if not isinstance(decision, dict) or decision.get("action") != "use_tool":
            trail.append(
                {"step": step, "action": "finish", "rationale": str(decision.get("rationale", ""))}
            )
            break

        tool = decision.get("tool")
        if tool not in TOOL_NAMES:
            trail.append({"step": step, "error": f"invalid tool {tool!r}"})
            break

        try:
            output = await tools.call(
                tool, query=decision.get("query"), fact_id=decision.get("fact_id")
            )
        except Exception as exc:  # noqa: BLE001 - a tool failure must not abort reconciliation
            output = f"{tool} raised: {exc}"

        entry = {
            "step": step,
            "tool": tool,
            "args": {"query": decision.get("query"), "fact_id": decision.get("fact_id")},
            "rationale": str(decision.get("rationale", "")),
            "result": output[:2000],
        }
        trail.append(entry)
        findings.append(f"[{tool}] {output}")

    used = sum(1 for e in trail if e.get("tool"))
    exhausted = used >= max_tool_calls

    final = await adjudicate_pair(
        a,
        evidence_a,
        b,
        evidence_b,
        provider,
        extra_context="\n\n".join(findings) or "(no additional context could be found)",
        allow_more_context=False,
    )
    trail.append(
        {
            "step": len(trail) + 1,
            "action": "final_classification",
            "verdict": final.relationship_type.value,
            "basis": final.reconciliation_basis,
            "budget_exhausted": exhausted,
        }
    )
    return ReconciliationResult(
        adjudication=final, trail=trail, tool_calls_used=used, budget_exhausted=exhausted
    )
