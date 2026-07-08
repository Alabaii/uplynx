from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Organization, OrgMember, User

DEFAULT_ORG_SLUG = "default"
DEFAULT_ORG_NAME = "My team"


def get_or_create_default_org(db: Session) -> Organization:
    org = db.scalar(select(Organization).where(Organization.slug == DEFAULT_ORG_SLUG))
    if not org:
        org = Organization(name=DEFAULT_ORG_NAME, slug=DEFAULT_ORG_SLUG)
        db.add(org)
        db.flush()
    return org


def ensure_membership(db: Session, user: User, org: Organization) -> OrgMember:
    member = db.scalar(select(OrgMember).where(OrgMember.org_id == org.id, OrgMember.user_id == user.id))
    if member:
        return member
    has_members = db.scalar(select(OrgMember.id).where(OrgMember.org_id == org.id).limit(1)) is not None
    member = OrgMember(org_id=org.id, user_id=user.id, role="member" if has_members else "owner")
    db.add(member)
    db.flush()
    return member


def get_user_org(db: Session, user: User) -> Organization:
    """Организация пользователя: в team-режиме — единственное членство (дефолтная организация)."""
    org = db.scalar(
        select(Organization)
        .join(OrgMember, OrgMember.org_id == Organization.id)
        .where(OrgMember.user_id == user.id)
        .order_by(OrgMember.id)
        .limit(1)
    )
    if org:
        return org
    org = get_or_create_default_org(db)
    ensure_membership(db, user, org)
    return org
