"""Ontology endpoint: canonical concepts grouped by the document that first
introduced them."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import project_scope
from app.api.schemas import ConceptOut, OntologyGroup, OntologyOut
from app.models.constants import CONCEPT_KINDS
from app.repository import list_concepts, list_documents
from app.repository.scope import ProjectScope

router = APIRouter(prefix="/projects/{project_id}/ontology", tags=["ontology"])


@router.get("", response_model=OntologyOut)
async def index(
    scope: ProjectScope = Depends(project_scope),
    kind: str | None = Query(None),
) -> OntologyOut:
    if kind is not None and kind not in CONCEPT_KINDS:
        kind = None
    concepts = await list_concepts(scope, kind=kind)
    names = {d.document_id: d.filename for d in await list_documents(scope)}

    grouped: dict = {}
    for c in concepts:
        grouped.setdefault(c.first_seen_document_id, []).append(ConceptOut.of(c))

    groups = [
        OntologyGroup(
            document_id=doc_id,
            document_filename=names.get(doc_id),
            concepts=items,
        )
        for doc_id, items in grouped.items()
    ]
    groups.sort(key=lambda g: (g.document_filename is None, g.document_filename or ""))
    return OntologyOut(groups=groups)
