from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from app.core.ratelimit import DatabaseRateLimiter, purge_stale_rate_limits
from app.models import RateLimitHit


def age_all_hits(db_session_factory, seconds: int) -> None:
    """Состаривает записи попыток — окно проверяется без ожидания в тесте."""
    with db_session_factory() as db:
        db.execute(update(RateLimitHit).values(hit_at=datetime.now(timezone.utc) - timedelta(seconds=seconds)))
        db.commit()


def test_database_limiter_window_and_expiry(db_session_factory, monkeypatch):
    monkeypatch.setattr("app.core.ratelimit.SessionLocal", db_session_factory)
    limiter = DatabaseRateLimiter("test", max_attempts=2, window_seconds=60)

    assert limiter.hit("k") is None
    assert limiter.hit("k") is None
    retry = limiter.hit("k")
    assert retry is not None and 0 < retry <= 60

    # разные ключи независимы
    assert limiter.hit("other") is None

    # окно истекло — снова можно, и просроченные строки ключа удалены
    age_all_hits(db_session_factory, seconds=120)
    assert limiter.hit("k") is None
    with db_session_factory() as db:
        rows = db.scalars(select(RateLimitHit).where(RateLimitHit.key == "k")).all()
        assert len(rows) == 1


def test_limiter_counts_are_shared_between_replicas(db_session_factory, monkeypatch):
    monkeypatch.setattr("app.core.ratelimit.SessionLocal", db_session_factory)
    # два экземпляра лимитера = два процесса API за балансировщиком
    first = DatabaseRateLimiter("test", max_attempts=2, window_seconds=60)
    second = DatabaseRateLimiter("test", max_attempts=2, window_seconds=60)

    assert first.hit("shared") is None
    assert second.hit("shared") is None
    # раньше вторая реплика имела собственный счётчик и пропустила бы попытку
    assert second.hit("shared") is not None


def test_limiter_scopes_do_not_share_counters(db_session_factory, monkeypatch):
    monkeypatch.setattr("app.core.ratelimit.SessionLocal", db_session_factory)
    login = DatabaseRateLimiter("login", max_attempts=1, window_seconds=60)
    register = DatabaseRateLimiter("register", max_attempts=1, window_seconds=60)

    assert login.hit("1.2.3.4") is None
    assert register.hit("1.2.3.4") is None
    assert login.hit("1.2.3.4") is not None


def test_reset_clears_attempts(db_session_factory, monkeypatch):
    monkeypatch.setattr("app.core.ratelimit.SessionLocal", db_session_factory)
    limiter = DatabaseRateLimiter("test", max_attempts=1, window_seconds=60)

    assert limiter.hit("k") is None
    assert limiter.hit("k") is not None
    limiter.reset("k")
    assert limiter.hit("k") is None


def test_purge_removes_abandoned_keys(db_session_factory, monkeypatch):
    monkeypatch.setattr("app.core.ratelimit.SessionLocal", db_session_factory)
    limiter = DatabaseRateLimiter("test", max_attempts=5, window_seconds=60)
    limiter.hit("forgotten")

    # ключ больше не обращается — его строки некому вычистить при попытке
    age_all_hits(db_session_factory, seconds=60 * 60 * 48)
    with db_session_factory() as db:
        assert purge_stale_rate_limits(db) == 1
        db.commit()
        assert db.scalars(select(RateLimitHit)).all() == []


def test_login_rate_limited_after_failures(client, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "login_rate_limit_attempts", 3)

    user = {"email": "victim@example.com", "password": "password123"}
    client.post("/api/v1/auth/register", json=user)

    wrong = {"email": user["email"], "password": "wrong-password"}
    for _ in range(3):
        assert client.post("/api/v1/auth/login", json=wrong).status_code == 401

    # лимит исчерпан: даже верный пароль получает 429 с Retry-After
    blocked = client.post("/api/v1/auth/login", json=user)
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers

    # другой email с того же IP не заблокирован
    other = {"email": "other@example.com", "password": "password123"}
    client.post("/api/v1/auth/register", json=other)
    assert client.post("/api/v1/auth/login", json=other).status_code == 200


def test_spraying_many_accounts_from_one_ip_is_limited(client, monkeypatch):
    """Перебор одного пароля по списку адресатов ключом ip+email не ловился.

    Каждый email давал свои пять попыток, поэтому атака с одного адреса шла
    сколько угодно долго — просто по новому аккаунту на каждый залп.
    """
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "login_ip_rate_limit_attempts", 4)

    for index in range(6):
        client.post(
            "/api/v1/auth/register", json={"email": f"user{index}@example.com", "password": "password123"}
        )

    statuses = [
        client.post(
            "/api/v1/auth/login", json={"email": f"user{index}@example.com", "password": "guess"}
        ).status_code
        for index in range(6)
    ]
    # первые попытки — обычный отказ, дальше вступает лимит на адрес
    assert statuses[:4] == [401, 401, 401, 401]
    assert statuses[4:] == [429, 429]

    # и верный пароль с того же адреса тоже упирается в лимит
    blocked = client.post("/api/v1/auth/login", json={"email": "user0@example.com", "password": "password123"})
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_successful_login_resets_ip_counter(client, monkeypatch):
    """Общий адрес (офис за NAT) не запирается чужими опечатками после успеха."""
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "login_ip_rate_limit_attempts", 3)

    for index in range(2):
        client.post(
            "/api/v1/auth/register", json={"email": f"mate{index}@example.com", "password": "password123"}
        )

    client.post("/api/v1/auth/login", json={"email": "mate0@example.com", "password": "typo"})
    client.post("/api/v1/auth/login", json={"email": "mate1@example.com", "password": "typo"})
    assert (
        client.post("/api/v1/auth/login", json={"email": "mate0@example.com", "password": "password123"}).status_code
        == 200
    )
    # счётчик адреса сброшен успешным входом — у коллеги снова полный запас
    assert (
        client.post("/api/v1/auth/login", json={"email": "mate1@example.com", "password": "password123"}).status_code
        == 200
    )


def test_successful_login_resets_counter(client, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "login_rate_limit_attempts", 3)

    user = {"email": "resetme@example.com", "password": "password123"}
    client.post("/api/v1/auth/register", json=user)

    wrong = {"email": user["email"], "password": "wrong-password"}
    client.post("/api/v1/auth/login", json=wrong)
    client.post("/api/v1/auth/login", json=wrong)
    assert client.post("/api/v1/auth/login", json=user).status_code == 200

    # счётчик сброшен — снова есть полный запас попыток
    client.post("/api/v1/auth/login", json=wrong)
    client.post("/api/v1/auth/login", json=wrong)
    assert client.post("/api/v1/auth/login", json=user).status_code == 200


def test_register_rate_limited_per_ip(client, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "register_rate_limit_attempts", 2)

    assert client.post("/api/v1/auth/register", json={"email": "a@example.com", "password": "password123"}).status_code == 201
    assert client.post("/api/v1/auth/register", json={"email": "b@example.com", "password": "password123"}).status_code == 201
    blocked = client.post("/api/v1/auth/register", json={"email": "c@example.com", "password": "password123"})
    assert blocked.status_code == 429


def make_request(headers: dict[str, str], peer: str = "10.0.0.1"):
    """Минимальный Request для client_ip: важны только заголовки и адрес соединения."""
    from starlette.requests import Request

    raw = [(key.lower().encode(), value.encode()) for key, value in headers.items()]
    return Request({"type": "http", "headers": raw, "client": (peer, 12345)})


def test_client_ip_takes_address_appended_by_own_proxy(monkeypatch):
    from app.api.v1.endpoints.auth import client_ip
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "trusted_proxy_hops", 0)

    # nginx смотрит наружу сам: его $remote_addr — последняя запись
    assert client_ip(make_request({"X-Forwarded-For": "203.0.113.7"})) == "203.0.113.7"
    # заголовка нет — остаётся адрес соединения
    assert client_ip(make_request({})) == "10.0.0.1"


def test_client_ip_ignores_spoofed_prefix(monkeypatch):
    from app.api.v1.endpoints.auth import client_ip
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "trusted_proxy_hops", 0)

    # клиент прислал свой X-Forwarded-For, nginx дописал реальный адрес в конец:
    # выбранным должен быть адрес от nginx, а не подделка клиента
    spoofed = "1.2.3.4, 5.6.7.8, 203.0.113.7"
    assert client_ip(make_request({"X-Forwarded-For": spoofed})) == "203.0.113.7"


def test_client_ip_with_tls_terminator_in_front(monkeypatch):
    from app.api.v1.endpoints.auth import client_ip
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "trusted_proxy_hops", 1)

    # Caddy дописал адрес клиента, nginx — адрес Caddy; подделка осталась слева
    header = "1.2.3.4, 203.0.113.7, 127.0.0.1"
    assert client_ip(make_request({"X-Forwarded-For": header})) == "203.0.113.7"

    # записей меньше, чем прокси по настройке — доверяем соединению, а не клиенту
    assert client_ip(make_request({"X-Forwarded-For": "1.2.3.4"})) == "10.0.0.1"


def test_login_limit_not_bypassed_by_forged_header(client, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "login_rate_limit_attempts", 3)
    monkeypatch.setattr(settings, "trusted_proxy_hops", 0)

    user = {"email": "brute@example.com", "password": "password123"}
    client.post("/api/v1/auth/register", json=user)
    wrong = {"email": user["email"], "password": "wrong-password"}

    # цепочка как в проде: nginx дописывает адрес своего собеседника в конец,
    # поэтому подделка клиента всегда оказывается слева от неё
    def through_nginx(forged: str) -> dict[str, str]:
        return {"X-Forwarded-For": f"{forged}, 203.0.113.7"}

    # каждая попытка приходит с новым поддельным X-Forwarded-For — раньше это
    # давало новый ключ лимитера и неограниченный перебор пароля
    for attempt in range(3):
        response = client.post(
            "/api/v1/auth/login", json=wrong, headers=through_nginx(f"9.9.9.{attempt}")
        )
        assert response.status_code == 401

    blocked = client.post("/api/v1/auth/login", json=user, headers=through_nginx("9.9.9.100"))
    assert blocked.status_code == 429

    # другой реальный адрес за тем же nginx по-прежнему не заблокирован
    other = {"email": "elsewhere@example.com", "password": "password123"}
    client.post("/api/v1/auth/register", json=other, headers={"X-Forwarded-For": "198.51.100.4"})
    assert (
        client.post(
            "/api/v1/auth/login", json=other, headers={"X-Forwarded-For": "9.9.9.100, 198.51.100.4"}
        ).status_code
        == 200
    )
