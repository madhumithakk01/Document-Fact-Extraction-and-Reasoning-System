"""Project-scoped data access.

The hard partition rule (BUILD_PHASES §4): no query, index, or code path spans
two ``project_id`` values. Every read here starts from :func:`scoped_select`,
which pins ``project_id`` before any other filter, and every write helper takes
a :class:`ProjectScope`. There is no function in this package that can address
data outside a single project.
"""

from app.repository.concepts import list_concepts
from app.repository.documents import (
    get_document,
    get_document_by_hash,
    list_documents,
)
from app.repository.facts import get_fact, list_facts
from app.repository.projects import (
    create_project,
    delete_project,
    get_project,
    list_projects,
)
from app.repository.relationships import get_relationship, list_relationships
from app.repository.scope import ProjectScope, scoped_select

__all__ = [
    "ProjectScope",
    "create_project",
    "delete_project",
    "get_document",
    "get_document_by_hash",
    "get_fact",
    "get_project",
    "get_relationship",
    "list_concepts",
    "list_documents",
    "list_facts",
    "list_projects",
    "list_relationships",
    "scoped_select",
]
