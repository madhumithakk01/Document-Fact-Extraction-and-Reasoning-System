"""Evaluation endpoint: grounding and verification quality, computed live from
``VerificationLog`` rows."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.api.deps import project_scope
from app.api.schemas import EvaluationOut
from app.models.fact import Fact
from app.models.verification_log import VerificationLog
from app.repository.scope import ProjectScope

router = APIRouter(prefix="/projects/{project_id}/evaluation", tags=["evaluation"])


@router.get("", response_model=EvaluationOut)
async def index(scope: ProjectScope = Depends(project_scope)) -> EvaluationOut:
    s = scope.session
    pid = scope.project_id

    grounding = {
        str(r): int(n)
        for r, n in (
            await s.execute(
                select(VerificationLog.result, func.count())
                .where(
                    VerificationLog.project_id == pid,
                    VerificationLog.stage == "grounding_check",
                )
                .group_by(VerificationLog.result)
            )
        ).all()
    }
    grounding_total = sum(grounding.values())
    grounding_pass = grounding.get("pass", 0)

    verify_breakdown = {
        str(r): int(n)
        for r, n in (
            await s.execute(
                select(VerificationLog.result, func.count())
                .where(
                    VerificationLog.project_id == pid,
                    VerificationLog.stage == "independent_verify",
                )
                .group_by(VerificationLog.result)
            )
        ).all()
    }

    facts_by_status = {
        str(r): int(n)
        for r, n in (
            await s.execute(
                select(Fact.verification_status, func.count())
                .where(Fact.project_id == pid)
                .group_by(Fact.verification_status)
            )
        ).all()
    }
    total_facts = sum(facts_by_status.values()) or 1

    return EvaluationOut(
        grounding_checks=grounding_total,
        grounding_pass_rate=(grounding_pass / grounding_total) if grounding_total else 0.0,
        independent_verify_breakdown=verify_breakdown,
        facts_by_status=facts_by_status,
        auto_correction_rate=facts_by_status.get("auto_corrected", 0) / total_facts,
        needs_review_rate=facts_by_status.get("needs_review", 0) / total_facts,
    )
