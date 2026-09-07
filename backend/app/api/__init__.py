"""HTTP routers."""

from app.api.documents import router as documents_router
from app.api.evaluation import router as evaluation_router
from app.api.facts import router as facts_router
from app.api.health import router as health_router
from app.api.ontology import router as ontology_router
from app.api.projects import router as projects_router
from app.api.query import router as query_router
from app.api.relationships import router as relationships_router

ALL_ROUTERS = (
    health_router,
    projects_router,
    documents_router,
    facts_router,
    relationships_router,
    ontology_router,
    evaluation_router,
    query_router,
)

__all__ = ["ALL_ROUTERS", "health_router"]
