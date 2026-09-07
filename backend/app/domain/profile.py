"""Pure functions over the domain profile: assign a document to a sub-cluster,
and fold a new document into the profile incrementally."""

from __future__ import annotations

import math
from collections.abc import Iterable

from app.domain.types import ClusterAssignment, DomainProfile, SubCluster

# A document whose embedding is at least this cosine-similar to a sub-cluster's
# centroid joins it; below this it forms a new sub-cluster. Calibrated against
# the local sentence-transformers model: documents on the same subject sit at
# ~0.84-0.90, an adjacent-but-different topic (e.g. macro data in a company-
# filings project) at ~0.60, unrelated material below ~0.45.
NEW_CLUSTER_THRESHOLD = 0.70


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _normalize(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n else list(v)


def _running_mean(current: list[float], count: int, addition: list[float]) -> list[float]:
    return _normalize(
        [(c * count + a) / (count + 1) for c, a in zip(current, addition, strict=True)]
    )


def _next_cluster_id(profile: DomainProfile) -> str:
    existing = {c.id for c in profile.sub_clusters}
    n = len(profile.sub_clusters) + 1
    while f"sc_{n}" in existing:
        n += 1
    return f"sc_{n}"


def assign_document(profile: DomainProfile, doc_embedding: list[float]) -> ClusterAssignment:
    """Place a document's embedding in the nearest sub-cluster, or start a new one."""
    if not profile.sub_clusters:
        return ClusterAssignment(
            sub_cluster_id="sc_1", similarity=1.0, is_new_cluster=True, off_domain=False
        )

    best_id, best_sim = max(
        ((c.id, _cosine(doc_embedding, c.centroid)) for c in profile.sub_clusters),
        key=lambda t: t[1],
    )
    if best_sim >= NEW_CLUSTER_THRESHOLD:
        return ClusterAssignment(
            sub_cluster_id=best_id,
            similarity=best_sim,
            is_new_cluster=False,
            off_domain=False,
        )
    return ClusterAssignment(
        sub_cluster_id=_next_cluster_id(profile),
        similarity=best_sim,
        is_new_cluster=True,
        off_domain=True,
    )


def update_profile(
    profile: DomainProfile,
    doc_embedding: list[float],
    assignment: ClusterAssignment,
    document_id: str,
    vocabulary_additions: Iterable[str] = (),
) -> DomainProfile:
    """Fold one document into the profile. No document already in the project is
    re-read; only the affected centroid and the vocabulary change."""
    n = profile.document_count
    centroid = (
        _normalize(list(doc_embedding))
        if profile.centroid_embedding is None
        else _running_mean(profile.centroid_embedding, n, doc_embedding)
    )

    clusters = {c.id: c for c in profile.sub_clusters}
    if assignment.is_new_cluster:
        clusters[assignment.sub_cluster_id] = SubCluster(
            id=assignment.sub_cluster_id,
            centroid=_normalize(list(doc_embedding)),
            document_ids=[document_id],
            size=1,
        )
    else:
        existing = clusters[assignment.sub_cluster_id]
        clusters[assignment.sub_cluster_id] = SubCluster(
            id=existing.id,
            centroid=_running_mean(existing.centroid, existing.size, doc_embedding),
            document_ids=[*existing.document_ids, document_id],
            size=existing.size + 1,
        )

    vocabulary = list(
        dict.fromkeys(
            [*profile.vocabulary, *(v.strip() for v in vocabulary_additions if v and v.strip())]
        )
    )

    return DomainProfile(
        centroid_embedding=centroid,
        sub_clusters=list(clusters.values()),
        vocabulary=vocabulary,
        document_count=n + 1,
    )
