"""Phase 11 exit criterion: the evaluation numbers are computed from real
VerificationLog rows and fact statuses on every request, not hardcoded."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.evaluation import compute_evaluation
from app.models.verification_log import VerificationLog
from app.repository import create_project, delete_project
from tests._env import db_reachable
from tests.comparison.conftest import make_document, make_fact

pytestmark = [pytest.mark.slow, pytest.mark.skipif(not db_reachable(), reason="no database")]


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine(get_settings().database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
        await s.rollback()
    await engine.dispose()


def _log(project_id, fact_id, stage, result) -> VerificationLog:  # noqa: ANN001
    return VerificationLog(
        log_id=uuid.uuid4(),
        project_id=project_id,
        fact_id=fact_id,
        stage=stage,
        result=result,
        detail={},
    )


async def test_report_is_derived_from_the_rows(session: AsyncSession) -> None:
    project = await create_project(session, "evaluation-test")
    pid = project.project_id
    try:
        # --- document A: 4 facts (3 verified, 1 needs_review) ---
        doc_a = make_document(pid, "doc-a.pdf")
        # the extractor proposed 6 candidates for this doc; 2 were dropped before
        # grounding (invalid schema), 4 were kept
        doc_a.extraction_stats = {
            "candidates_returned": 6,
            "candidates_kept": 4,
            "dropped_invalid": 2,
        }
        session.add(doc_a)
        await session.flush()
        a_facts = [
            make_fact(
                pid,
                doc_a.document_id,
                entity="X",
                attribute=f"m{i}",
                value={"comparator": "eq", "number": i},
                period="FY24",
                status=("needs_review" if i == 3 else "verified"),
            )
            for i in range(4)
        ]
        session.add_all(a_facts)
        await session.flush()
        for f in a_facts:
            session.add(_log(pid, f.fact_id, "grounding_check", "pass"))
            session.add(
                _log(
                    pid,
                    f.fact_id,
                    "independent_verify",
                    "supported" if f.verification_status == "verified" else "partially_supported",
                )
            )

        # --- document B: 2 facts (1 auto_corrected, 1 rejected) + a grounding fail ---
        doc_b = make_document(pid, "doc-b.pdf")
        doc_b.extraction_stats = {"candidates_returned": 2, "candidates_kept": 2}
        session.add(doc_b)
        await session.flush()
        b_ok = make_fact(
            pid,
            doc_b.document_id,
            entity="Y",
            attribute="k",
            value={"comparator": "eq", "number": 9},
            period="FY24",
            status="auto_corrected",
        )
        b_bad = make_fact(
            pid,
            doc_b.document_id,
            entity="Y",
            attribute="j",
            value={"comparator": "eq", "number": 1},
            period="FY24",
            status="rejected",
        )
        session.add_all([b_ok, b_bad])
        await session.flush()
        session.add(_log(pid, b_ok.fact_id, "grounding_check", "pass"))
        session.add(_log(pid, b_ok.fact_id, "independent_verify", "partially_supported"))
        session.add(_log(pid, b_ok.fact_id, "independent_verify", "supported"))  # recheck
        session.add(_log(pid, b_bad.fact_id, "grounding_check", "fail"))
        await session.commit()

        report = await compute_evaluation(session, pid)

        # grounding: 5 pass, 1 fail
        assert report.grounding_checks == 6
        assert report.grounding_pass == 5
        assert abs(report.grounding_pass_rate - 5 / 6) < 1e-9

        # honest survivorship: 8 candidates proposed (6 + 2), 2 dropped before
        # grounding, 1 dropped at grounding; yield is over all 8, not just the 6
        # that reached the check
        assert report.candidates_considered == 8
        assert report.candidates_kept == 6
        assert report.candidates_dropped_pre_grounding == 2
        assert report.candidates_dropped_for_grounding == 1
        assert abs(report.grounding_yield_rate - 5 / 8) < 1e-9
        assert report.grounding_note

        # independent verify raw verdicts: 3 supported, 1 partial (A) + 1 partial + 1 supported (B)
        assert report.independent_verify_calls == 6
        assert report.independent_verify_breakdown["supported"] == 4
        assert report.independent_verify_breakdown["partially_supported"] == 2

        # fact status rollup
        assert report.facts_total == 6
        assert report.facts_by_status == {
            "verified": 3,
            "needs_review": 1,
            "auto_corrected": 1,
            "rejected": 1,
        }
        assert abs(report.verified_rate - 0.5) < 1e-9
        assert abs(report.needs_review_rate - 1 / 6) < 1e-9

        # per-document
        by_name = {d.filename: d for d in report.per_document}
        assert by_name["doc-a.pdf"].facts_total == 4
        assert by_name["doc-a.pdf"].grounding_pass_rate == 1.0
        assert by_name["doc-b.pdf"].grounding_checks == 2
        assert abs(by_name["doc-b.pdf"].grounding_pass_rate - 0.5) < 1e-9
        assert by_name["doc-a.pdf"].candidates_dropped_for_grounding == 0
        assert by_name["doc-b.pdf"].candidates_dropped_for_grounding == 1

        # timeline: cumulative, one point per document in processing order
        assert [t.index for t in report.timeline] == [1, 2]
        assert report.timeline[0].cumulative_facts == 4
        assert report.timeline[0].grounding_pass_rate == 1.0
        assert report.timeline[1].cumulative_facts == 6
        assert abs(report.timeline[1].grounding_pass_rate - 5 / 6) < 1e-9

        # mutate the data -> the report changes (nothing is cached/hardcoded)
        session.add(_log(pid, b_bad.fact_id, "grounding_check", "fail"))
        await session.commit()
        again = await compute_evaluation(session, pid)
        assert again.grounding_checks == 7
        assert again.grounding_pass_rate != report.grounding_pass_rate
    finally:
        await session.rollback()
        await delete_project(session, pid)
        await session.commit()


async def test_empty_project_is_all_zeros(session: AsyncSession) -> None:
    project = await create_project(session, "evaluation-empty")
    try:
        report = await compute_evaluation(session, project.project_id)
        assert report.grounding_checks == 0
        assert report.grounding_pass_rate == 0.0
        assert report.facts_total == 0
        assert report.per_document == []
        assert report.timeline == []
    finally:
        await delete_project(session, project.project_id)
        await session.commit()
