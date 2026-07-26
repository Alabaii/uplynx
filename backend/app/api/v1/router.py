from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    auth,
    config,
    incidents,
    maintenance,
    meta,
    monitors,
    orgs,
    plans,
    push,
    secrets,
    status,
    telegram,
)

api_router = APIRouter()
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(config.router, prefix="/config", tags=["config"])
api_router.include_router(incidents.router, tags=["incidents"])
api_router.include_router(maintenance.router, prefix="/maintenance", tags=["maintenance"])
api_router.include_router(meta.router, tags=["meta"])
api_router.include_router(monitors.router, tags=["monitors"])
api_router.include_router(orgs.router, prefix="/orgs", tags=["orgs"])
api_router.include_router(plans.router, prefix="/plans", tags=["plans"])
api_router.include_router(push.router, prefix="/push", tags=["push"])
api_router.include_router(secrets.router, prefix="/secrets", tags=["secrets"])
api_router.include_router(status.router, prefix="/status", tags=["status"])
api_router.include_router(telegram.router, prefix="/telegram", tags=["telegram"])
