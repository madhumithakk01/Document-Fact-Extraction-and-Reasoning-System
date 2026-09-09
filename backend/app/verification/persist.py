"""Apply verification outcomes to stored facts and write the log.

``fact_ids`` must be in the same order as ``result.verifications`` -- both come
from the extraction run's fact list, and ``persist_facts`` returns its rows in
that order.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fact import Fact
from app.models.verification_log import VerificationLog
from app.verification.audit import build_correction_record
from app.verification.schema import VerificationResult


async def persist_verification(
    session: AsyncSession,
    project_id: uuid.UUID,
    fact_ids: Sequence[uuid.UUID],
    result: VerificationResult,
) -> None:
    if len(fact_ids) != len(result.verifications):
        raise ValueError(
            f"fact_ids ({len(fact_ids)}) and verifications "
            f"({len(result.verifications)}) are not aligned"
        )

    rows = {
        r.fact_id: r
        for r in (
            await session.execute(
                select(Fact).where(Fact.project_id == project_id, Fact.fact_id.in_(list(fact_ids)))
            )
        )
        .scalars()
        .all()
    }

    for fact_id, fv in zip(fact_ids, result.verifications, strict=True):
        row = rows.get(fact_id)
        if row is None:
            continue
        row.verification_status = fv.final_status.value
        row.verifier_confidence = fv.verifier_confidence
        if fv.notes:
            row.notes = [*(row.notes or []), *fv.notes]

        if fv.corrected and fv.corrected_fact is not None:
            c = fv.corrected_fact
            record = build_correction_record(row, c)
            if record is not None:
                row.corrections = [*(row.corrections or []), record]
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
