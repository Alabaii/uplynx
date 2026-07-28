import json
import logging

import requests
from pywebpush import WebPushException, webpush
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPSConnection
from urllib3.connectionpool import HTTPSConnectionPool
from urllib3.poolmanager import PoolManager
from urllib3.util import connection as urllib3_connection

from app.core.config import get_settings
from app.core.ssrf import BlockedTargetError, resolve_public_address
from app.models import PushSubscription

logger = logging.getLogger(__name__)


class PushSubscriptionGone(Exception):
    """Push-сервис ответил 404/410 — подписка мертва, её нужно удалить из БД."""


def pinned_session(address: str) -> requests.Session:
    """requests-сессия, которая ходит ТОЛЬКО на проверенный адрес.

    Проверить адрес и передать pywebpush имя хоста недостаточно: requests
    резолвит его заново перед соединением, и хост под контролем арендатора
    успевает подменить ответ DNS на приватный (rebinding) — ровно то окно,
    которое для мониторов закрыто пиннингом в services/checks.py.

    Приколот только адрес TCP-соединения; в URL остаётся имя хоста, поэтому
    SNI и проверка сертификата работают как при обычном запросе — подменять
    их вручную (и рисковать доставкой) не нужно.

    trust_env=False обязателен: с HTTPS_PROXY в окружении requests соединяется
    с прокси, а имя хоста резолвит уже он — выбранный нами адрес перестаёт
    что-либо значить, и окно rebinding открывается заново. Пиннинг и прокси
    несовместимы по смыслу, поэтому здесь ходим напрямую.
    """

    class _PinnedConnection(HTTPSConnection):
        def _new_conn(self):  # type: ignore[no-untyped-def]
            return urllib3_connection.create_connection(
                (address, self.port),
                self.timeout,
                source_address=self.source_address,
                socket_options=self.socket_options,
            )

    class _PinnedPool(HTTPSConnectionPool):
        ConnectionCls = _PinnedConnection

    class _PinnedPoolManager(PoolManager):
        def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
            super().__init__(*args, **kwargs)
            self.pool_classes_by_scheme = dict(self.pool_classes_by_scheme, https=_PinnedPool)

    class _PinnedAdapter(HTTPAdapter):
        def init_poolmanager(self, connections, maxsize, block=False, **kwargs):  # type: ignore[no-untyped-def]
            self.poolmanager = _PinnedPoolManager(
                num_pools=connections, maxsize=maxsize, block=block, **kwargs
            )

    session = requests.Session()
    session.trust_env = False
    session.mount("https://", _PinnedAdapter())
    return session


def push_enabled() -> bool:
    settings = get_settings()
    return bool(settings.vapid_public_key and settings.vapid_private_key)


def send_web_push(subscription: PushSubscription, title: str, body: str, url: str = "/") -> bool:
    settings = get_settings()
    try:
        # адрес проверен при подписке, но DNS мог смениться с тех пор — воркер
        # перепроверяет его перед каждой отправкой, как и цели мониторов, и
        # соединение прикалывается к проверенному адресу (см. pinned_session)
        address = resolve_public_address(
            subscription.endpoint, allow_private=settings.allow_private_targets
        )
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
            # address=None — проверка снята allow_private_targets (on-prem):
            # там push-сервис может быть и внутренним, пиннинг не нужен
            requests_session=pinned_session(address) if address else None,
        )
    except WebPushException as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        if status_code in (404, 410):
            raise PushSubscriptionGone from exc
        logger.warning("push service rejected notification (status %s): %s", status_code, exc)
        return False
    return True
