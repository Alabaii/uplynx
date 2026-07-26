import re
import secrets

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Organization, OrgMember, User

DEFAULT_ORG_SLUG = "default"
DEFAULT_ORG_NAME = "My team"
# запас до лимита колонки (160): к слагу может добавиться суффикс от коллизии
PERSONAL_SLUG_MAX_LENGTH = 40


def get_or_create_default_org(db: Session) -> Organization:
    org = db.scalar(select(Organization).where(Organization.slug == DEFAULT_ORG_SLUG))
    if not org:
        org = Organization(name=DEFAULT_ORG_NAME, slug=DEFAULT_ORG_SLUG)
        db.add(org)
        db.flush()
    return org


def _slug_base(email: str) -> str:
    """Читаемая основа слага из локальной части email; слаг неизменяем после создания."""
    local_part = email.split("@", 1)[0].lower()
    slug = re.sub(r"[^a-z0-9]+", "-", local_part).strip("-")[:PERSONAL_SLUG_MAX_LENGTH].strip("-")
    return slug or "workspace"


def create_personal_org(db: Session, user: User) -> Organization:
    """Собственный воркспейс регистрирующегося: он в нём owner и единственный участник.

    В SaaS-режиме общая организация означала бы, что любой зарегистрировавшийся
    видит и правит мониторы всех остальных клиентов платформы: org_id у них
    совпадает, поэтому ни проверки в запросах, ни RLS такой доступ не отличат.
    """
    base = _slug_base(user.email)
    slug = base
    while db.scalar(select(Organization.id).where(Organization.slug == slug)):
        # у чужого клиента может быть тот же локальный адрес на другом домене —
        # случайный суффикс разводит их без раскрытия, сколько таких уже есть
        slug = f"{base}-{secrets.token_hex(3)}"
    org = Organization(name=base, slug=slug)
    db.add(org)
    db.flush()
    return org


def enforce_member_quota(db: Session, org: Organization) -> None:
    """403, если в enterprise-режиме добавление ещё одного участника превысит quota_members.

    В team-режиме действует глобальный env-лимит (TEAM_MAX_USERS), квоты организации игнорируются.
    """
    if get_settings().deployment_mode != "enterprise" or org.quota_members is None:
        return
    current = db.scalar(select(func.count()).select_from(OrgMember).where(OrgMember.org_id == org.id)) or 0
    if current + 1 > org.quota_members:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Member quota reached: organization allows at most {org.quota_members} members",
        )


def ensure_membership(db: Session, user: User, org: Organization) -> OrgMember:
    member = db.scalar(select(OrgMember).where(OrgMember.org_id == org.id, OrgMember.user_id == user.id))
    if member:
        return member
    has_members = db.scalar(select(OrgMember.id).where(OrgMember.org_id == org.id).limit(1)) is not None
    member = OrgMember(org_id=org.id, user_id=user.id, role="member" if has_members else "owner")
    db.add(member)
    db.flush()
    return member
