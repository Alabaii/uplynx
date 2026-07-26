import json
import logging

from pywebpush import WebPushException, webpush

from app.core.config import get_settings
from app.core.ssrf import BlockedTargetError, validate_public_url
from app.models import PushSubscription

logger = logging.getLogger(__name__)


class PushSubscriptionGone(Exception):
    """Push-сервис ответил 404/410 — подписка мертва, её нужно удалить из БД."""


def push_enabled() -> bool:
    settings = get_settings()
    return bool(settings.vapid_public_key and settings.vapid_private_key)


def send_web_push(subscription: PushSubscription, title: str, body: str, url: str = "/") -> bool:
    settings = get_settings()
    try:
        # адрес проверен при подписке, но DNS мог смениться с тех пор — воркер
        # перепроверяет его перед каждой отправкой, как и цели мониторов
        validate_public_url(subscription.endpoint, allow_private=settings.allow_private_targets)
    except BlockedTargetError as exc:
        logger.warning("push endpoint %s is not publicly routable: %s", subscription.endpoint, exc)
        return False
    try:
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
            },
            data=json.dumps({"title": title, "body": body, "url": url}),
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_subject},
        )
    except WebPushException as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        if status_code in (404, 410):
            raise PushSubscriptionGone from exc
        logger.warning("push service rejected notification (status %s): %s", status_code, exc)
        return False
    return True
