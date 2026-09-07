"""Typed structures for the domain profile."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SubCluster(BaseModel):
    id: str
    centroid: list[float]
    document_ids: list[str] = Field(default_factory=list)
    size: int = 0


class DomainProfile(BaseModel):
    centroid_embedding: list[float] | None = None
    sub_clusters: list[SubCluster] = Field(default_factory=list)
    vocabulary: list[str] = Field(default_factory=list)
    document_count: int = 0

    @classmethod
    def load(cls, raw: dict[str, Any] | None) -> DomainProfile:
        return cls.model_validate(raw or {})

    def dump(self) -> dict[str, Any]:
        return self.model_dump()

    def cluster(self, cluster_id: str) -> SubCluster | None:
        return next((c for c in self.sub_clusters if c.id == cluster_id), None)


class ClusterAssignment(BaseModel):
    sub_cluster_id: str
    similarity: float  # cosine similarity to the chosen cluster's centroid
    is_new_cluster: bool
    # true when a new cluster formed *and* the project already had one -- i.e.
    # this document looks topically different from what is already there
    off_domain: bool
