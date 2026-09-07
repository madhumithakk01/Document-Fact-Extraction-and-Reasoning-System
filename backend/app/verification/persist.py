"""Apply verification outcomes to stored facts and write the log.

``fact_rows`` must be the rows returned by ``persist_facts`` for this document,
in the same order as ``result.verifications`` -- both derive from the extraction
run's fact list.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fact import Fact
from app.models.verification_log import VerificationLog
from app.verification.schema import VerificationResult


async def persist_verification(
    session: AsyncSession,
    project_id: uuid.UUID,
    fact_rows: Sequence[Fact],
    result: VerificationResult,
) -> None:
    if len(fact_rows) != len(result.verifications):
        raise ValueError(
            f"fact_rows ({len(fact_rows)}) and verifications "
            f"({len(result.verifications)}) are not aligned"
        )

    for row, fv in zip(fact_rows, result.verifications, strict=True):
        row.verification_status = fv.final_status.value
        row.verifier_confidence = fv.verifier_confidence
        if fv.notes:
            row.notes = [*(row.notes or []), *fv.notes]

        if fv.corrected and fv.corrected_fact is not None:
            c = fv.corrected_fact
            row.entity = c.entity
            row.entity_resolved = c.entity_resolved
            row.attribute = c.attribute
            row.value = c.value.model_dump(exclude_none=True)
            row.period = c.period.model_dump(exclude_none=True)
            row.qualifiers = c.qualifiers

        for entry in fv.log:
            session.add(
                VerificationLog(
                    log_id=uuid.uuid4(),
                    project_id=project_id,
                    fact_id=row.fact_id,
                    stage=entry.stage.value,
                    result=entry.result,
                    issue=entry.issue,
                    detail=entry.detail,
                )
            )

    await session.flush()
