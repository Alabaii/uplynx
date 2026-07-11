from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Plan
from app.schemas import PlanRead
from app.services.plans import ensure_default_plans

router = APIRouter()


@router.get("", response_model=list[PlanRead])
def list_public_plans(db: Session = Depends(get_db)) -> list[Plan]:
    """Публичная витрина тарифов — для страницы /pricing и лендинга (без авторизации).

    Секретов в тарифах нет; та же таблица редактируется суперадмином в /admin.
    """
    ensure_default_plans(db)
    return list(db.scalars(select(Plan).order_by(Plan.sort_order)))
