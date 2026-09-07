"""Compute the evaluation report from raw rows."""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.evaluation.schema import DocumentEvaluation, EvaluationReport, TimelinePoint
from app.models.document import Document
from app.models.fact import Fact
from app.models.verification_log import VerificationLog


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


async def compute_evaluation(session: AsyncSession, project_id: uuid.UUID) -> EvaluationReport:
    # --- facts: id -> (document_id, status) ---
    fact_rows = (
        await session.execute(
            select(Fact.fact_id, Fact.document_id, Fact.verification_status).where(
                Fact.project_id == project_id
            )
        )
    ).all()
    fact_document = {r[0]: r[1] for r in fact_rows}
    status_by_document: dict[uuid.UUID, Counter[str]] = defaultdict(Counter)
    overall_status: Counter[str] = Counter()
    for _fid, did, status in fact_rows:
        status_by_document[did][status] += 1
        overall_status[status] += 1

    # --- verification logs ---
    log_rows = (
        await session.execute(
            select(VerificationLog.fact_id, VerificationLog.stage, VerificationLog.result).where(
                VerificationLog.project_id == project_id
            )
        )
    ).all()
    grounding_by_document: dict[uuid.UUID, Counter[str]] = defaultdict(Counter)
    grounding_overall: Counter[str] = Counter()
    verify_overall: Counter[str] = Counter()
    for fid, stage, result in log_rows:
        did = fact_document.get(fid)
        if stage == "grounding_check":
            grounding_overall[result] += 1
            if did is not None:
                grounding_by_document[did][result] += 1
        elif stage == "independent_verify":
            verify_overall[result] += 1

    grounding_checks = sum(grounding_overall.values())
    grounding_pass = grounding_overall.get("pass", 0)
    facts_total = sum(overall_status.values())

    # --- documents in processing order ---
    documents = (
        (
            await session.execute(
                select(Document)
                .where(Document.project_id == project_id)
                .order_by(Document.created_at.asc())
            )
        )
        .scalars()
        .all()
    )

    per_document: list[DocumentEvaluation] = []
    timeline: list[TimelinePoint] = []
    cum_status: Counter[str] = Counter()
    cum_grounding: Counter[str] = Counter()

    for i, doc in enumerate(documents, start=1):
        d_status = status_by_document.get(doc.document_id, Counter())
        d_grounding = grounding_by_document.get(doc.document_id, Counter())
        d_ground_total = sum(d_grounding.values())
        d_ground_pass = d_grounding.get("pass", 0)
        d_facts = sum(d_status.values())

        per_document.append(
            DocumentEvaluation(
                document_id=doc.document_id,
                filename=doc.filename,
                processed_at=doc.uploaded_at or doc.created_at,
                facts_total=d_facts,
                facts_by_status=dict(d_status),
                grounding_checks=d_ground_total,
                grounding_pass=d_ground_pass,
                grounding_pass_rate=_rate(d_ground_pass, d_ground_total),
            )
        )

        cum_status.update(d_status)
        cum_grounding.update(d_grounding)
        cum_facts = sum(cum_status.values())
        cum_ground_total = sum(cum_grounding.values())
        timeline.append(
            TimelinePoint(
                index=i,
                document_id=doc.document_id,
                filename=doc.filename,
                cumulative_facts=cum_facts,
                grounding_pass_rate=_rate(cum_grounding.get("pass", 0), cum_ground_total),
                verified_rate=_rate(cum_status.get("verified", 0), cum_facts),
                needs_review_rate=_rate(cum_status.get("needs_review", 0), cum_facts),
            )
        )

    return EvaluationReport(
        grounding_checks=grounding_checks,
        grounding_pass=grounding_pass,
        grounding_pass_rate=_rate(grounding_pass, grounding_checks),
        independent_verify_calls=sum(verify_overall.values()),
        independent_verify_breakdown=dict(verify_overall),
        facts_total=facts_total,
        facts_by_status=dict(overall_status),
        verified_rate=_rate(overall_status.get("verified", 0), facts_total),
        auto_correction_rate=_rate(overall_status.get("auto_corrected", 0), facts_total),
        needs_review_rate=_rate(overall_status.get("needs_review", 0), facts_total),
        rejected_rate=_rate(overall_status.get("rejected", 0), facts_total),
        per_document=per_document,
        timeline=timeline,
    )
