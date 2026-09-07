"""Project-scoped document reads."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from app.models.document import Document
from app.repository.scope import ProjectScope, scoped_select


async def list_documents(scope: ProjectScope) -> Sequence[Document]:
    stmt = scoped_select(Document, scope).order_by(Document.created_at.desc())
    return (await scope.session.execute(stmt)).scalars().all()


async def get_document(scope: ProjectScope, document_id: uuid.UUID) -> Document | None:
    stmt = scoped_select(Document, scope, Document.document_id == document_id)
    return (await scope.session.execute(stmt)).scalar_one_or_none()


async def get_document_by_hash(scope: ProjectScope, content_hash: str) -> Document | None:
    stmt = scoped_select(Document, scope, Document.content_hash == content_hash)
    return (await scope.session.execute(stmt)).scalar_one_or_none()
