from app.core.ratelimit import SlidingWindowLimiter


def test_sliding_window_limits_and_expires():
    now = [0.0]
    limiter = SlidingWindowLimiter(max_attempts=2, window_seconds=10, clock=lambda: now[0])

    assert limiter.hit("k") is None
    assert limiter.hit("k") is None
    retry = limiter.hit("k")
    assert retry is not None and 0 < retry <= 10

    # окно истекло — снова можно
    now[0] = 10.1
    assert limiter.hit("k") is None

    # разные ключи независимы
    assert limiter.hit("other") is None


def test_reset_clears_attempts():
    limiter = SlidingWindowLimiter(max_attempts=1, window_seconds=60)
    assert limiter.hit("k") is None
    assert limiter.hit("k") is not None
    limiter.reset("k")
    assert limiter.hit("k") is None


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
