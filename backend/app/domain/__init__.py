"""Domain profiling and incremental ingestion (BUILD_PHASES §7).

A project carries a ``domain_profile``: a rolling centroid embedding, a set of
sub-clusters formed from its documents' embeddings, and the accumulated
canonical vocabulary. When a new document is added, it is embedded once, placed
in the nearest sub-cluster (or forms a new one, with a soft "off-domain"
signal), and the profile is updated incrementally -- the documents already in
the project are never re-embedded or re-compared.
"""

from app.domain.document_embedding import compute_document_embedding
from app.domain.incremental import profile_new_document
from app.domain.profile import (
    NEW_CLUSTER_THRESHOLD,
    assign_document,
    update_profile,
)
from app.domain.types import ClusterAssignment, DomainProfile, SubCluster

__all__ = [
    "NEW_CLUSTER_THRESHOLD",
    "ClusterAssignment",
    "DomainProfile",
    "SubCluster",
    "assign_document",
    "compute_document_embedding",
    "profile_new_document",
    "update_profile",
]
