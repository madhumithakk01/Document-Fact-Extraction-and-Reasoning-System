"""Evaluation endpoint: grounding and verification quality, computed live from
``VerificationLog`` rows and current fact statuses."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import project_scope
from app.evaluation import EvaluationReport, compute_evaluation
from app.repository.scope import ProjectScope

router = APIRouter(prefix="/projects/{project_id}/evaluation", tags=["evaluation"])


@router.get("", response_model=EvaluationReport)
async def index(scope: ProjectScope = Depends(project_scope)) -> EvaluationReport:
    return await compute_evaluation(scope.session, scope.project_id)
