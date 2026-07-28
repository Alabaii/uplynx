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

# Потолок ожидания ответа push-сервиса. Без него pywebpush передаёт в requests
# timeout=None, то есть ждёт вечно. Отправка идёт через asyncio.to_thread, а его
# пул потоков (min(32, cpu+4) — на двух ядрах это шесть) общий с записью
# результатов проверок: несколько подписок на молчащий хост исчерпывали пул, и
# воркер переставал сохранять результаты и подтверждать сообщения. Адрес хоста
# задаёт арендатор, так что это управляемая им остановка проверок всей платформы.
PUSH_TIMEOUT_SECONDS = 10


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

    session = _NoRedirectSession()
    session.trust_env = False
    session.mount("https://", _PinnedAdapter())
    return session


class _NoRedirectSession(requests.Session):
    """Сессия, которая не ходит по редиректам.

    Пиннинг действует на адрес, проверенный ДО запроса. Редирект уводит на
    адрес, который никто не проверял, а `Location: http://...` — ещё и мимо
    приколотого адаптера: он навешен на https, а http обслуживает дефолтный,
    с повторным резолвом имени. Проверено: 302 на внутренний адрес возвращал
    тело внутреннего сервиса.

    У мониторов цепочка редиректов обрабатывается вручную с перепроверкой
    каждого хопа (services/checks.py). Здесь она не нужна вовсе: endpoint
    выдаёт сам push-сервис, перенаправлять ему некуда. pywebpush поднимает
    WebPushException на любой ответ больше 202, поэтому оставшийся 3xx станет
    обычной ошибкой доставки.
    """

    def resolve_redirects(self, resp, req, **kwargs):  # type: ignore[no-untyped-def]
        logger.warning("push service replied with a redirect (%s); not following it", resp.status_code)
        return iter(())


def push_enabled() -> bool:
    settings = get_settings()
    return bool(settings.vapid_public_key and settings.vapid_private_key)


def send_web_push(subscription: PushSubscription, title: str, body: str, url: str = "/") -> bool:
    settings = get_settings()
    if not settings.allow_private_targets and not subscription.endpoint.lower().startswith("https://"):
        # Пиннинг стоит на https-адаптере: по http requests пошёл бы дефолтным,
        # с повторным резолвом имени. Подписка на http отвергается при создании,
        # эта проверка прикрывает строки, заведённые до неё
        logger.warning("refusing to send push over non-https endpoint")
        return False
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
            timeout=PUSH_TIMEOUT_SECONDS,
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
