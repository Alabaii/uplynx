from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import OrgContext, get_current_org_member
from app.core.config import get_settings
from app.core.database import get_db
from app.core.ssrf import BlockedTargetError, validate_public_url
from app.models import PushSubscription
from app.schemas import PushConfigRead, PushSubscribe, PushUnsubscribe
from app.services.webpush import push_enabled

router = APIRouter()


def validate_push_endpoint(endpoint: str) -> None:
    """Адрес push-сервиса приходит от клиента, а ходит по нему воркер изнутри сети.

    Без проверки это второй путь к внутренней инфраструктуре в обход SSRF-защиты
    мониторов: подписка на http://169.254.169.254/... заставила бы воркер слать
    туда POST при каждом алерте.

    Здесь, как и при создании монитора, проверка без резолва — мгновенный отказ
    на литеральный приватный адрес; с резолвом её повторяет воркер перед отправкой.

    Только https: спецификация Web Push другого и не допускает (браузер иных
    endpoint'ов и не выдаёт), а у воркера пиннинг проверенного адреса стоит на
    https-адаптере (services/webpush.py) — подписка на http ушла бы мимо него
    дефолтным адаптером, который резолвит имя заново, и окно DNS rebinding
    открылось бы снова. Под allow_private_targets проверка не нужна: там SSRF-
    защита снята целиком и осознанно, пиннинга нет по определению.
    """
    allow_private = get_settings().allow_private_targets
    if not allow_private and not endpoint.lower().startswith("https://"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Push endpoint must use https",
        )
    try:
        validate_public_url(endpoint, allow_private=allow_private, resolve=False)
    except BlockedTargetError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/config", response_model=PushConfigRead)
def read_config() -> PushConfigRead:
    if not push_enabled():
        return PushConfigRead(enabled=False)
    return PushConfigRead(enabled=True, public_key=get_settings().vapid_public_key)


@router.post("/subscribe", status_code=status.HTTP_204_NO_CONTENT)
def subscribe(
    payload: PushSubscribe,
    ctx: OrgContext = Depends(get_current_org_member),
    db: Session = Depends(get_db),
) -> None:
    if not push_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Push notifications are disabled")
    validate_push_endpoint(payload.endpoint)
    # подписка принадлежит организации: повторная подписка того же устройства
    # обновляет ключи и владельца ВНУТРИ воркспейса, а в другом воркспейсе
    # заводит свою — уведомления адресуются по org_id, и участник двух
    # организаций должен получать алерты обеих
    subscription = db.scalar(
        select(PushSubscription).where(
            PushSubscription.endpoint == payload.endpoint,
            PushSubscription.org_id == ctx.org.id,
        )
    )
    if subscription:
        subscription.user_id = ctx.user.id
        subscription.p256dh = payload.keys.p256dh
        subscription.auth = payload.keys.auth
    else:
        db.add(
            PushSubscription(
                org_id=ctx.org.id,
                user_id=ctx.user.id,
                endpoint=payload.endpoint,
                p256dh=payload.keys.p256dh,
                auth=payload.keys.auth,
            )
        )
    db.commit()


@router.post("/unsubscribe", status_code=status.HTTP_204_NO_CONTENT)
def unsubscribe(
    payload: PushUnsubscribe,
    ctx: OrgContext = Depends(get_current_org_member),
    db: Session = Depends(get_db),
) -> None:
    subscription = db.scalar(
        select(PushSubscription).where(
            PushSubscription.endpoint == payload.endpoint,
            PushSubscription.user_id == ctx.user.id,
            PushSubscription.org_id == ctx.org.id,
        )
    )
    if subscription:
        db.delete(subscription)
        db.commit()
