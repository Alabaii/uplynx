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
