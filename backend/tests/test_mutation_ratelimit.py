import asyncio

from app.core.config import get_settings
from app.core.ratelimit import DatabaseRateLimiter, get_mutation_limiter


def tighten_limit(monkeypatch, attempts: int) -> None:
    monkeypatch.setattr(get_settings(), "mutation_rate_limit_attempts", attempts)
    get_mutation_limiter.cache_clear()


def test_limiter_does_not_run_inside_the_event_loop(client, auth_headers, monkeypatch):
    """Лимитер делает три запроса к БД; в async-middleware это остановило бы весь процесс."""
    original = DatabaseRateLimiter.hit
    ran_in_loop = []

    def spy(self, key):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            ran_in_loop.append(False)
        else:
            ran_in_loop.append(True)
        return original(self, key)

    monkeypatch.setattr(DatabaseRateLimiter, "hit", spy)
    client.post("/api/v1/monitors", headers=auth_headers, json={})

    assert ran_in_loop == [False]


def test_mutations_rate_limited_per_user(client, auth_headers, monkeypatch):
    tighten_limit(monkeypatch, 3)
    for _ in range(3):
        response = client.post("/api/v1/monitors", headers=auth_headers, json={})
        assert response.status_code != 429
    response = client.post("/api/v1/monitors", headers=auth_headers, json={})
    assert response.status_code == 429
    assert "Retry-After" in response.headers


def test_reads_not_limited(client, auth_headers, monkeypatch):
    tighten_limit(monkeypatch, 1)
    client.post("/api/v1/monitors", headers=auth_headers, json={})
    for _ in range(5):
        assert client.get("/api/v1/monitors", headers=auth_headers).status_code == 200


def test_auth_endpoints_excluded(client, monkeypatch):
    # у /auth свои лимиты — мутационный не должен добавлять 429 к логину
    tighten_limit(monkeypatch, 1)
    payload = {"email": "mut-limit@example.com", "password": "password123"}
    client.post("/api/v1/auth/register", json=payload)
    for _ in range(3):
        assert client.post("/api/v1/auth/login", json=payload).status_code == 200


def test_unauthenticated_mutations_limited_by_ip(client, monkeypatch):
    tighten_limit(monkeypatch, 2)
    for _ in range(2):
        assert client.post("/api/v1/monitors", json={}).status_code == 401
    assert client.post("/api/v1/monitors", json={}).status_code == 429
