from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import OrgContext, get_current_org_member, require_role
from app.core.database import get_db
from app.models import ConfigVersion
from app.schemas import ConfigRead, ConfigRollback, ConfigUpload, ConfigVersionRead
from app.services.audit import record
from app.services.config_sync import latest_config_version, next_config_version, rollback_config, upload_config

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
    # версия вычисляется заранее в той же транзакции — аудит коммитится вместе с загрузкой
    version_number = next_config_version(db, ctx.org.id)
    record(
        db,
        org_id=ctx.org.id,
        user_id=ctx.user.id,
        action="config.upload",
        entity="config",
        entity_id=str(version_number),
        payload={"version": version_number},
    )
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
def versions(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx: OrgContext = Depends(get_current_org_member),
    db: Session = Depends(get_db),
) -> list[ConfigVersionRead]:
    # выбираем поля списка, а не сущность целиком: content каждой версии — до
    # полумегабайта, и он всё равно отбрасывается при сериализации
    rows = db.execute(
        select(ConfigVersion.id, ConfigVersion.version, ConfigVersion.format, ConfigVersion.created_at)
        .where(ConfigVersion.org_id == ctx.org.id)
        .order_by(ConfigVersion.version.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [
        ConfigVersionRead(id=row.id, version=row.version, format=row.format, created_at=row.created_at)
        for row in rows
    ]


@router.post("/rollback", response_model=ConfigVersionRead)
def rollback(
    payload: ConfigRollback,
    ctx: OrgContext = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> ConfigVersion:
    record(
        db,
        org_id=ctx.org.id,
        user_id=ctx.user.id,
        action="config.rollback",
        entity="config",
        entity_id=str(payload.version),
        payload={"version": payload.version},
    )
    return rollback_config(db, ctx.user, ctx.org, payload.version)
