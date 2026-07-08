from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import OrgContext, get_current_org_member, require_role
from app.core.database import get_db
from app.models import ConfigVersion
from app.schemas import ConfigRead, ConfigRollback, ConfigUpload, ConfigVersionRead
from app.services.config_sync import latest_config_version, rollback_config, upload_config

router = APIRouter()


@router.get("", response_model=ConfigRead)
def get_config(ctx: OrgContext = Depends(get_current_org_member), db: Session = Depends(get_db)) -> ConfigRead:
    version = latest_config_version(db, ctx.org.id)
    if not version:
        return ConfigRead(content="version: 1\nmonitors: []\n", format="yaml", version=None)
    return ConfigRead(content=version.content, format=version.format, version=version.version)


@router.post("", response_model=ConfigVersionRead)
def post_config(
    payload: ConfigUpload,
    ctx: OrgContext = Depends(require_role("member")),
    db: Session = Depends(get_db),
) -> ConfigVersion:
    return upload_config(db, ctx.user, ctx.org, payload.content, payload.format)


@router.get("/download")
def download_config(ctx: OrgContext = Depends(get_current_org_member), db: Session = Depends(get_db)) -> Response:
    version = latest_config_version(db, ctx.org.id)
    content = version.content if version else "version: 1\nmonitors: []\n"
    media_type = "application/json" if version and version.format == "json" else "application/x-yaml"
    filename = f"monitor-config-v{version.version if version else 0}.{version.format if version else 'yaml'}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/versions", response_model=list[ConfigVersionRead])
def versions(ctx: OrgContext = Depends(get_current_org_member), db: Session = Depends(get_db)) -> list[ConfigVersion]:
    return list(
        db.scalars(
            select(ConfigVersion)
            .where(ConfigVersion.org_id == ctx.org.id)
            .order_by(ConfigVersion.version.desc())
        ).all()
    )


@router.post("/rollback", response_model=ConfigVersionRead)
def rollback(
    payload: ConfigRollback,
    ctx: OrgContext = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> ConfigVersion:
    return rollback_config(db, ctx.user, ctx.org, payload.version)
