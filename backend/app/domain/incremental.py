"""Fold a freshly ingested document into the project's domain profile.

Runs after the new document has been verified and before comparison. It embeds
the document once, assigns it to a sub-cluster, updates the rolling profile, and
records the placement on the document row -- the documents already in the
project are untouched.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.document_embedding import compute_document_embedding
from app.domain.profile import assign_document, update_profile
from app.domain.types import ClusterAssignment, DomainProfile
from app.models.document import Document
from app.models.fact import Fact
from app.models.project import Project
from app.providers import get_embedding_provider
from app.providers.base import EmbeddingProvider

logger = logging.getLogger(__name__)


async def _document_vocabulary(
    session: AsyncSession, project_id: uuid.UUID, document_id: uuid.UUID
) -> list[str]:
    rows = (
        (
            await session.execute(
                select(Fact.entity)
                .where(Fact.project_id == project_id, Fact.document_id == document_id)
                .distinct()
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def profile_new_document(
    session: AsyncSession,
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    chunk_texts: Sequence[str],
    *,
    embedder: EmbeddingProvider | None = None,
) -> ClusterAssignment:
    embedder = embedder or get_embedding_provider()

    doc_embedding = await compute_document_embedding(chunk_texts, provider=embedder)

    project = await session.get(Project, project_id)
    if project is None:  # pragma: no cover - defensive
        raise ValueError(f"project {project_id} not found")

    profile = DomainProfile.load(project.domain_profile)
    assignment = assign_document(profile, doc_embedding)

    vocabulary = await _document_vocabulary(session, project_id, document_id)
    updated = update_profile(profile, doc_embedding, assignment, str(document_id), vocabulary)
    project.domain_profile = updated.dump()

    document = await session.get(Document, document_id)
    if document is not None:
        document.doc_embedding = doc_embedding
        document.sub_cluster_id = assignment.sub_cluster_id
        document.off_domain = assignment.off_domain

    await session.flush()
    logger.info(
        "document %s placed in %s (similarity %.2f, off_domain=%s); project now has "
        "%d document(s) across %d sub-cluster(s)",
        document_id,
        assignment.sub_cluster_id,
        assignment.similarity,
        assignment.off_domain,
        updated.document_count,
        len(updated.sub_clusters),
    )
    return assignment
