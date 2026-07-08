from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas import DeploymentLimits, MetaRead
from app.services.email import email_enabled

router = APIRouter()


@router.get("/meta", response_model=MetaRead)
def meta() -> MetaRead:
    settings = get_settings()
    limits = None
    if settings.deployment_mode == "team":
        limits = DeploymentLimits(max_users=settings.team_max_users, max_monitors=settings.team_max_monitors)
    return MetaRead(deployment_mode=settings.deployment_mode, limits=limits, email_enabled=email_enabled())
