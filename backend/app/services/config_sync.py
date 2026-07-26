import json
from datetime import datetime, timezone
from typing import Any

import yaml
from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.ssrf import BlockedTargetError, validate_public_url
from app.models import ConfigVersion, Monitor, Organization, User
from app.schemas import ConfigDocument, ConfigMonitor, MonitorCreate, MonitorUpdate
from app.services.plans import (
    count_enabled_monitors,
    enforce_plan_monitor_limits,
    validate_plan_interval,
)


# сколько последних версий конфига держим на организацию: снимок пишется на
# каждое изменение монитора, откатываются же на недавние
MAX_CONFIG_VERSIONS_KEPT = 50


def validate_target_url(url: str | None) -> None:
    """Быстрая (без DNS) проверка URL монитора при создании/загрузке конфига.

    Полную проверку с резолвом делает воркер перед запросом; здесь — мгновенный
    фидбек на литеральный приватный IP / localhost. URL с плейсхолдером ${VAR}
    пропускаем: реальное значение известно только воркеру.
    """
    if not url or "${" in url:
        return
    try:
        validate_public_url(url, allow_private=get_settings().allow_private_targets, resolve=False)
    except BlockedTargetError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def parse_config(content: str, fmt: str) -> ConfigDocument:
    try:
        raw: Any = json.loads(content) if fmt == "json" else yaml.safe_load(content)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid {fmt}: {exc}") from exc
    if raw is None:
        raw = {}
    try:
        return ConfigDocument.model_validate(raw)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.errors()) from exc


def dump_config(document: ConfigDocument, fmt: str = "yaml") -> str:
    data = document.model_dump(exclude_none=True)
    for monitor in data.get("monitors", []):
        # дефолтное значение не шумит в конфиге
        if monitor.get("confirmations") == 1:
            monitor.pop("confirmations")
    if fmt == "json":
        return json.dumps(data, indent=2, ensure_ascii=False)
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def latest_config_version(db: Session, org_id: int) -> ConfigVersion | None:
    return db.scalar(
        select(ConfigVersion)
        .where(ConfigVersion.org_id == org_id)
        .order_by(ConfigVersion.version.desc())
        .limit(1)
    )


def next_config_version(db: Session, org_id: int) -> int:
    current = db.scalar(select(func.max(ConfigVersion.version)).where(ConfigVersion.org_id == org_id)) or 0
    return current + 1


def prune_config_versions(db: Session, org_id: int, keep: int = MAX_CONFIG_VERSIONS_KEPT) -> None:
    """Оставляет организации только последние keep версий конфига.

    Снимок конфига пишется на КАЖДОЕ изменение монитора, а не только на явную
    загрузку: без обрезки таблица растёт вместе с обычной работой, и каждая
    строка несёт до полумегабайта содержимого. Что менялось и кем — остаётся
    в audit_log, здесь нужны только версии, на которые реально откатываются.
    """
    oldest_kept = db.scalar(
        select(ConfigVersion.version)
        .where(ConfigVersion.org_id == org_id)
        .order_by(ConfigVersion.version.desc())
        .offset(keep - 1)
        .limit(1)
    )
    if oldest_kept is not None:
        db.execute(
            delete(ConfigVersion).where(
                ConfigVersion.org_id == org_id, ConfigVersion.version < oldest_kept
            )
        )


def create_config_version(db: Session, user: User, org: Organization, content: str, fmt: str) -> ConfigVersion:
    version = ConfigVersion(user_id=user.id, org_id=org.id, version=next_config_version(db, org.id), content=content, format=fmt)
    db.add(version)
    db.flush()
    prune_config_versions(db, org.id)
    return version


def payload_config_json(payload: ConfigMonitor | MonitorCreate) -> dict[str, Any]:
    """Гибкие поля монитора для Monitor.config_json; confirmations=1 (дефолт) не храним."""
    config_json = payload.model_dump(exclude={"id", "name", "type", "url", "interval", "enabled"}, exclude_none=True)
    if config_json.get("confirmations") == 1:
        config_json.pop("confirmations")
    return config_json


def monitor_to_config(monitor: Monitor) -> ConfigMonitor:
    data = dict(monitor.config_json or {})
    return ConfigMonitor(
        id=monitor.slug,
        name=monitor.name,
        type=monitor.type,  # type: ignore[arg-type]
        url=monitor.url,
        interval=monitor.interval,
        expected=data.get("expected"),
        steps=data.get("steps"),
        enabled=monitor.enabled,
        confirmations=data.get("confirmations", 1),
        renotify_interval_minutes=data.get("renotify_interval_minutes"),
    )


def build_config_from_db(db: Session, org: Organization) -> ConfigDocument:
    monitors = db.scalars(
        select(Monitor)
        .where(Monitor.org_id == org.id, Monitor.archived_at.is_(None))
        .order_by(Monitor.slug)
    ).all()
    return ConfigDocument(version=1, monitors=[monitor_to_config(m) for m in monitors])


def enforce_monitor_limit(db: Session, org: Organization, new_enabled_count: int) -> None:
    """new_enabled_count — сколько enabled-мониторов будет у организации после изменения.

    team: глобальный env-лимит на инсталляцию; enterprise: quota_monitors организации (null = безлимит).
    """
    settings = get_settings()
    if settings.deployment_mode == "team":
        others = db.scalar(
            select(func.count())
            .select_from(Monitor)
            .where(Monitor.enabled.is_(True), Monitor.archived_at.is_(None), Monitor.org_id != org.id)
        ) or 0
        if others + new_enabled_count > settings.team_max_monitors:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Monitor limit reached: team deployment allows at most {settings.team_max_monitors} enabled monitors",
            )
        return
    if org.quota_monitors is not None and new_enabled_count > org.quota_monitors:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Monitor quota reached: organization allows at most {org.quota_monitors} enabled monitors",
        )


def resync_monitors(db: Session, user: User, org: Organization, document: ConfigDocument) -> None:
    # архивные в синхронизации не участвуют: их слаг свободен и может быть занят
    # новым монитором, а сама архивация — не «отсутствие в конфиге»
    existing = {
        m.slug: m
        for m in db.scalars(
            select(Monitor).where(Monitor.org_id == org.id, Monitor.archived_at.is_(None))
        ).all()
    }
    incoming = {m.id: m for m in document.monitors}
    now = datetime.now(timezone.utc)

    for slug, cfg in incoming.items():
        validate_target_url(cfg.url)
        config_json = payload_config_json(cfg)
        monitor = existing.get(slug)
        if monitor:
            monitor.name = cfg.name or slug
            monitor.type = cfg.type
            monitor.url = cfg.url
            monitor.interval = cfg.interval
            monitor.config_json = config_json
            monitor.enabled = cfg.enabled
            monitor.status = monitor.status if cfg.enabled else "paused"
            monitor.next_run_at = now if cfg.enabled else None
        else:
            db.add(
                Monitor(
                    user_id=user.id,
                    org_id=org.id,
                    slug=slug,
                    name=cfg.name or slug,
                    type=cfg.type,
                    status="paused" if not cfg.enabled else "pending",
                    url=cfg.url,
                    interval=cfg.interval,
                    config_json=config_json,
                    enabled=cfg.enabled,
                    next_run_at=now if cfg.enabled else None,
                )
            )

    for slug, monitor in existing.items():
        if slug not in incoming:
            monitor.enabled = False
            monitor.status = "paused"
            monitor.next_run_at = None


def upload_config(db: Session, user: User, org: Organization, content: str, fmt: str) -> ConfigVersion:
    document = parse_config(content, fmt)
    enforce_monitor_limit(db, org, sum(1 for m in document.monitors if m.enabled))
    # гейтинг плана: конфиг описывает целевое состояние организации целиком
    enforce_plan_monitor_limits(
        db,
        org,
        enabled_total=sum(1 for m in document.monitors if m.enabled),
        enabled_browser=sum(1 for m in document.monitors if m.enabled and m.type == "browser"),
    )
    for cfg in document.monitors:
        if cfg.enabled:
            validate_plan_interval(db, org, cfg.type, cfg.interval)
    version = create_config_version(db, user, org, content, fmt)
    resync_monitors(db, user, org, document)
    db.commit()
    db.refresh(version)
    return version


def rollback_config(db: Session, user: User, org: Organization, version_number: int) -> ConfigVersion:
    target = db.scalar(
        select(ConfigVersion).where(
            ConfigVersion.org_id == org.id,
            ConfigVersion.version == version_number,
        )
    )
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Config version not found")
    return upload_config(db, user, org, target.content, target.format)


def persist_monitors_as_config(db: Session, user: User, org: Organization, fmt: str = "yaml") -> ConfigVersion:
    document = build_config_from_db(db, org)
    content = dump_config(document, fmt)
    version = create_config_version(db, user, org, content, fmt)
    db.commit()
    db.refresh(version)
    return version


def create_monitor_from_payload(db: Session, user: User, org: Organization, payload: MonitorCreate) -> Monitor:
    validate_target_url(payload.url)
    if db.scalar(
        select(Monitor).where(
            Monitor.org_id == org.id, Monitor.slug == payload.id, Monitor.archived_at.is_(None)
        )
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Monitor already exists")
    if payload.enabled:
        org_enabled = db.scalar(
            select(func.count())
            .select_from(Monitor)
            .where(Monitor.enabled.is_(True), Monitor.archived_at.is_(None), Monitor.org_id == org.id)
        ) or 0
        enforce_monitor_limit(db, org, org_enabled + 1)
        enabled_total, enabled_browser = count_enabled_monitors(db, org)
        enforce_plan_monitor_limits(
            db,
            org,
            enabled_total=enabled_total + 1,
            enabled_browser=enabled_browser + (1 if payload.type == "browser" else 0),
        )
        validate_plan_interval(db, org, payload.type, payload.interval)
    config_json = payload_config_json(payload)
    monitor = Monitor(
        user_id=user.id,
        org_id=org.id,
        slug=payload.id,
        name=payload.name or payload.id,
        type=payload.type,
        status="pending" if payload.enabled else "paused",
        url=payload.url,
        interval=payload.interval,
        config_json=config_json,
        enabled=payload.enabled,
        next_run_at=datetime.now(timezone.utc) if payload.enabled else None,
    )
    db.add(monitor)
    db.flush()
    persist_monitors_as_config(db, user, org)
    db.refresh(monitor)
    return monitor


def update_monitor_from_payload(db: Session, user: User, org: Organization, monitor: Monitor, payload: MonitorUpdate) -> Monitor:
    data = payload.model_dump(exclude_unset=True)
    if "url" in data:
        validate_target_url(data["url"])
    will_be_enabled = data.get("enabled", monitor.enabled)
    if will_be_enabled:
        validate_plan_interval(db, org, monitor.type, data.get("interval", monitor.interval))
    if data.get("enabled") and not monitor.enabled:
        # включение ранее выключенного — это +1 к счётчикам плана
        enabled_total, enabled_browser = count_enabled_monitors(db, org)
        enforce_plan_monitor_limits(
            db,
            org,
            enabled_total=enabled_total + 1,
            enabled_browser=enabled_browser + (1 if monitor.type == "browser" else 0),
        )
    config = dict(monitor.config_json or {})
    for field in ["name", "url", "interval", "enabled"]:
        if field in data:
            setattr(monitor, field, data[field])
    if "expected" in data:
        config["expected"] = data["expected"]
    if "steps" in data:
        config["steps"] = data["steps"]
    if "confirmations" in data:
        if data["confirmations"] and data["confirmations"] > 1:
            config["confirmations"] = data["confirmations"]
        else:
            config.pop("confirmations", None)
    if "renotify_interval_minutes" in data:
        if data["renotify_interval_minutes"]:
            config["renotify_interval_minutes"] = data["renotify_interval_minutes"]
        else:
            config.pop("renotify_interval_minutes", None)
    monitor.config_json = config
    if monitor.enabled and monitor.next_run_at is None:
        monitor.next_run_at = datetime.now(timezone.utc)
    if not monitor.enabled:
        monitor.status = "paused"
        monitor.next_run_at = None
    db.flush()
    persist_monitors_as_config(db, user, org)
    db.refresh(monitor)
    return monitor
