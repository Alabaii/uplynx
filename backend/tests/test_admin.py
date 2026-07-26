from types import SimpleNamespace

import pytest

from app.api.v1.endpoints.admin import get_publisher
from app.core.config import get_settings
from app.main import app


class FakePublisher:
    """Подменяет RabbitPublisher: depths=None имитирует недоступный брокер."""

    def __init__(self, depths: dict[str, int] | None = None) -> None:
        self.depths = depths
        self.closed = False

    def check_queue_depth(self, queue: str) -> int:
        if self.depths is None:
            raise RuntimeError("rabbit down")
        return self.depths[queue]

    def declare_queue(self, queue: str):
        if self.depths is None:
            raise RuntimeError("rabbit down")
        return SimpleNamespace(method=SimpleNamespace(message_count=self.depths[queue]))

    def close(self) -> None:
        self.closed = True


@pytest.fixture()
def superuser_headers(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "superuser_emails", "root@example.com")
    payload = {"email": "root@example.com", "password": "password123"}
    client.post("/api/v1/auth/register", json=payload)
    token = client.post("/api/v1/auth/login", json=payload).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_admin_requires_superuser(client, auth_headers):
    assert client.get("/api/v1/admin/plans").status_code == 401
    for path in ("/api/v1/admin/plans", "/api/v1/admin/orgs", "/api/v1/admin/overview"):
        response = client.get(path, headers=auth_headers)
        assert response.status_code == 403, path


def test_me_reports_superuser_flag(client, auth_headers, superuser_headers):
    assert client.get("/api/v1/auth/me", headers=auth_headers).json()["is_superuser"] is False
    assert client.get("/api/v1/auth/me", headers=superuser_headers).json()["is_superuser"] is True


def test_plans_seeded_and_sorted(client, superuser_headers):
    response = client.get("/api/v1/admin/plans", headers=superuser_headers)
    assert response.status_code == 200
    plans = response.json()
    assert [plan["slug"] for plan in plans] == ["free", "pro", "business"]
    business = plans[2]
    assert business["price_monthly_kopeks"] == 399000
    assert business["max_members"] is None


def test_plan_update(client, superuser_headers):
    client.get("/api/v1/admin/plans", headers=superuser_headers)
    response = client.put(
        "/api/v1/admin/plans/pro",
        headers=superuser_headers,
        json={"price_monthly_kopeks": 119000, "max_monitors": 60, "annual_discount_pct": 20},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["price_monthly_kopeks"] == 119000
    assert body["max_monitors"] == 60
    assert body["annual_discount_pct"] == 20
    # не переданные поля не тронуты
    assert body["min_interval_seconds"] == 60
    assert body["updated_at"] is not None


def test_plan_update_unlimited_members(client, superuser_headers):
    client.get("/api/v1/admin/plans", headers=superuser_headers)
    response = client.put(
        "/api/v1/admin/plans/pro",
        headers=superuser_headers,
        json={"unlimited_members": True},
    )
    assert response.status_code == 200
    assert response.json()["max_members"] is None
    response = client.put(
        "/api/v1/admin/plans/pro",
        headers=superuser_headers,
        json={"max_members": 10},
    )
    assert response.json()["max_members"] == 10


def test_plan_update_validation_and_missing(client, superuser_headers):
    client.get("/api/v1/admin/plans", headers=superuser_headers)
    response = client.put(
        "/api/v1/admin/plans/pro",
        headers=superuser_headers,
        json={"price_monthly_kopeks": -5},
    )
    assert response.status_code == 422
    response = client.put(
        "/api/v1/admin/plans/nope",
        headers=superuser_headers,
        json={"price_monthly_kopeks": 100},
    )
    assert response.status_code == 404


def test_orgs_list_and_plan_change(client, superuser_headers):
    response = client.get("/api/v1/admin/orgs", headers=superuser_headers)
    assert response.status_code == 200
    orgs = response.json()
    assert len(orgs) >= 1
    org = orgs[0]
    assert org["plan_slug"] == "free"
    assert org["members_count"] >= 1

    response = client.put(
        f"/api/v1/admin/orgs/{org['id']}/plan",
        headers=superuser_headers,
        json={"plan_slug": "business"},
    )
    assert response.status_code == 200
    assert response.json()["plan_slug"] == "business"

    response = client.put(
        f"/api/v1/admin/orgs/{org['id']}/plan",
        headers=superuser_headers,
        json={"plan_slug": "nope"},
    )
    assert response.status_code == 404


def test_overview_counts_and_rabbit_down(client, auth_headers, superuser_headers):
    app.dependency_overrides[get_publisher] = lambda: FakePublisher(None)
    response = client.get("/api/v1/admin/overview", headers=superuser_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["users_total"] >= 2
    assert body["orgs_total"] >= 1
    assert body["scheduler"]["stale"] is True
    assert body["queues"] is None


def test_overview_queue_depths(client, superuser_headers):
    depths = {
        "http_checks.v2": 3,
        "browser_checks.v2": 0,
        "http_checks.dlq": 1,
        "browser_checks.dlq": 0,
    }
    app.dependency_overrides[get_publisher] = lambda: FakePublisher(depths)
    response = client.get("/api/v1/admin/overview", headers=superuser_headers)
    assert response.status_code == 200
    queues = {item["name"]: item["depth"] for item in response.json()["queues"]}
    assert queues == depths


def test_publisher_dependency_closes_the_connection(monkeypatch):
    """Соединение с брокером открывается на каждый обзор — закрыть его обязаны оба пути.

    Раньше close() стоял только в ветке сбоя, и успешный запрос оставлял
    соединение висеть до таймаута на стороне RabbitMQ.
    """
    monkeypatch.setattr("app.api.v1.endpoints.admin.RabbitPublisher", FakePublisher)

    generator = get_publisher()
    publisher = next(generator)
    with pytest.raises(StopIteration):
        next(generator)
    assert publisher.closed is True

    # и когда обработчик упал, соединение тоже не остаётся
    generator = get_publisher()
    publisher = next(generator)
    with pytest.raises(RuntimeError):
        generator.throw(RuntimeError("handler failed"))
    assert publisher.closed is True
