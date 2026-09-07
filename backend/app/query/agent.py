"""Bounded gathering loop for the reasoning console.

At most ``MAX_STEPS`` tool calls. Each step the model either requests a
``search_facts`` or ``get_relationships`` call, or concludes. Every call and its
result is kept in the trace. The loop returns the set of fact ids gathered.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.providers.base import CompletionRequest, LLMProvider, ProviderError
from app.query.schema import QueryTraceEntry
from app.query.tools import TOOL_NAMES, QueryTools

logger = logging.getLogger(__name__)

MAX_STEPS = 5

_SYSTEM = """\
You gather the facts needed to answer a question about one project's verified
facts. You have two tools:
- search_facts(query, fact_kind?): find facts by meaning and by keyword.
- get_relationships(fact_id): list how a fact relates to others (corroborates,
  contradicts, reconciled_by_context).

Each step, either call one tool that would bring in facts you still need, or
conclude when you have enough to answer. Prefer a few targeted searches over
many. When a fact looks like it might be disputed, call get_relationships on it.
You get at most five tool calls.\
"""

_STEP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "action": {"type": "string", "enum": ["search_facts", "get_relationships", "conclude"]},
        "query": {"type": ["string", "null"]},
        "fact_kind": {
            "type": ["string", "null"],
            "enum": ["quantitative", "status", "qualitative", None],
        },
        "fact_id": {"type": ["string", "null"]},
        "rationale": {"type": "string"},
    },
    "required": ["action", "query", "fact_kind", "fact_id", "rationale"],
}


async def gather(
    question: str,
    tools: QueryTools,
    provider: LLMProvider,
    *,
    max_steps: int = MAX_STEPS,
) -> tuple[list[uuid.UUID], list[QueryTraceEntry], int]:
    fact_ids: dict[uuid.UUID, None] = {}
    trace: list[QueryTraceEntry] = []
    findings: list[str] = []

    for step in range(1, max_steps + 1):
        history = "\n\n".join(findings) if findings else "(nothing gathered yet)"
        user = (
            f"QUESTION: {question}\n\n"
            f"GATHERED SO FAR ({step - 1}/{max_steps} tool calls used):\n{history}\n\n"
            f"Decide the next step."
        )
        try:
            result = await provider.complete(
                CompletionRequest(
                    system=_SYSTEM, user=user, json_schema=_STEP_SCHEMA, temperature=0.0
                )
            )
            decision = result.json()
        except (ProviderError, ValueError) as exc:
            logger.warning("query planning step failed: %s", exc)
            trace.append(QueryTraceEntry(step=step, tool="error", result=str(exc)[:200]))
            break

        action = decision.get("action") if isinstance(decision, dict) else None
        if action not in TOOL_NAMES:
            trace.append(
                QueryTraceEntry(
                    step=step, tool="conclude", rationale=str(decision.get("rationale", ""))
                )
            )
            break

        rationale = str(decision.get("rationale", ""))
        if action == "search_facts":
            query = (decision.get("query") or question).strip()
            facts = await tools.search_facts(query, fact_kind=decision.get("fact_kind"))
            for f in facts:
                fact_ids[f.fact_id] = None
            rendered = await tools.render_search(facts)
            trace.append(
                QueryTraceEntry(
                    step=step,
                    tool="search_facts",
                    args={"query": query, "fact_kind": decision.get("fact_kind")},
                    rationale=rationale,
                    result=rendered[:2000],
                )
            )
            findings.append(f"[search_facts {query!r}]\n{rendered}")
        else:  # get_relationships
            raw_id = decision.get("fact_id") or ""
            try:
                fid = uuid.UUID(str(raw_id))
            except ValueError:
                trace.append(
                    QueryTraceEntry(
                        step=step, tool="get_relationships", result=f"invalid fact id {raw_id!r}"
                    )
                )
                findings.append(f"[get_relationships] invalid fact id {raw_id!r}")
                continue
            rels = await tools.get_relationships(fid)
            rendered = await tools.render_relationships(rels)
            trace.append(
                QueryTraceEntry(
                    step=step,
                    tool="get_relationships",
                    args={"fact_id": str(fid)},
                    rationale=rationale,
                    result=rendered[:2000],
                )
            )
            findings.append(f"[get_relationships {fid}]\n{rendered}")

    used = sum(1 for e in trace if e.tool in TOOL_NAMES)
    return list(fact_ids), trace, used
