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
