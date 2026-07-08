from fastapi import APIRouter

from app.api.v1.endpoints import auth, config, meta, monitors, orgs, telegram

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(config.router, prefix="/config", tags=["config"])
api_router.include_router(meta.router, tags=["meta"])
api_router.include_router(monitors.router, tags=["monitors"])
api_router.include_router(orgs.router, prefix="/orgs", tags=["orgs"])
api_router.include_router(telegram.router, prefix="/telegram", tags=["telegram"])
