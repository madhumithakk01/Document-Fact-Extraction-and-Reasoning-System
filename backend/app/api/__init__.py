"""HTTP routers. Resource routers are added as later phases land; for now only
the operational health router is registered."""

from app.api.health import router as health_router

__all__ = ["health_router"]
