def test_register_login_and_config_upload(client):
    user = {"email": "a@example.com", "password": "password123"}
    assert client.post("/api/v1/auth/register", json=user).status_code == 201
    login = client.post("/api/v1/auth/login", json=user)
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    content = """
version: 1
monitors:
  - id: api-health
    type: http
    url: https://example.com/health
    interval: 60
    expected:
      status: 200
      body_contains: ok
"""
    uploaded = client.post("/api/v1/config", json={"content": content, "format": "yaml"}, headers=headers)
    assert uploaded.status_code == 200
    assert uploaded.json()["version"] == 1

    monitors = client.get("/api/v1/monitors", headers=headers)
    assert monitors.status_code == 200
    assert monitors.json()[0]["id"] == "api-health"

    versions = client.get("/api/v1/config/versions", headers=headers)
    assert versions.status_code == 200
    assert len(versions.json()) == 1


def test_monitor_crud_creates_config_versions(client, auth_headers):
    response = client.post(
        "/api/v1/monitors",
        json={"id": "site", "type": "http", "url": "https://example.com", "interval": 60},
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["status"] == "pending"

    update = client.put("/api/v1/monitors/site", json={"enabled": False}, headers=auth_headers)
    assert update.status_code == 200
    assert update.json()["status"] == "paused"

    versions = client.get("/api/v1/config/versions", headers=auth_headers).json()
    assert len(versions) == 2

    history = client.get("/api/v1/history", headers=auth_headers)
    assert history.status_code == 200


def test_auth_me(client, auth_headers):
    response = client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "user@example.com"
    assert isinstance(body["id"], int)

    assert client.get("/api/v1/auth/me").status_code == 401


def test_garbage_jwt_subject_returns_401(client):
    from app.core.security import create_access_token

    token = create_access_token("not-a-number")
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_disabled_monitor_survives_config_round_trip(client, auth_headers):
    client.post(
        "/api/v1/monitors",
        json={"id": "site", "type": "http", "url": "https://example.com", "interval": 60},
        headers=auth_headers,
    )
    client.put("/api/v1/monitors/site", json={"enabled": False}, headers=auth_headers)

    config = client.get("/api/v1/config", headers=auth_headers).json()
    assert "enabled: false" in config["content"]

    # заливаем тот же конфиг обратно — монитор должен остаться выключенным
    client.post("/api/v1/config", json={"content": config["content"], "format": "yaml"}, headers=auth_headers)
    monitors = client.get("/api/v1/monitors", headers=auth_headers).json()
    assert monitors[0]["enabled"] is False
    assert monitors[0]["status"] == "paused"


def test_team_user_limit(client, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "deployment_mode", "team")
    monkeypatch.setattr(settings, "team_max_users", 1)

    first = client.post("/api/v1/auth/register", json={"email": "a@example.com", "password": "password123"})
    assert first.status_code == 201
    second = client.post("/api/v1/auth/register", json={"email": "b@example.com", "password": "password123"})
    assert second.status_code == 403

    monkeypatch.setattr(settings, "deployment_mode", "enterprise")
    third = client.post("/api/v1/auth/register", json={"email": "b@example.com", "password": "password123"})
    assert third.status_code == 201


def test_team_monitor_limit(client, auth_headers, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "deployment_mode", "team")
    monkeypatch.setattr(settings, "team_max_monitors", 1)

    first = client.post(
        "/api/v1/monitors",
        json={"id": "one", "type": "http", "url": "https://example.com", "interval": 60},
        headers=auth_headers,
    )
    assert first.status_code == 201
    second = client.post(
        "/api/v1/monitors",
        json={"id": "two", "type": "http", "url": "https://example.com", "interval": 60},
        headers=auth_headers,
    )
    assert second.status_code == 403

    content = """
version: 1
monitors:
  - id: one
    type: http
    url: https://example.com
    interval: 60
  - id: two
    type: http
    url: https://example.com
    interval: 60
"""
    uploaded = client.post("/api/v1/config", json={"content": content, "format": "yaml"}, headers=auth_headers)
    assert uploaded.status_code == 403

    monkeypatch.setattr(settings, "deployment_mode", "enterprise")
    third = client.post(
        "/api/v1/monitors",
        json={"id": "two", "type": "http", "url": "https://example.com", "interval": 60},
        headers=auth_headers,
    )
    assert third.status_code == 201


def test_meta_endpoint(client, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "deployment_mode", "team")
    body = client.get("/api/v1/meta").json()
    assert body["deployment_mode"] == "team"
    assert body["limits"] == {"max_users": settings.team_max_users, "max_monitors": settings.team_max_monitors}

    monkeypatch.setattr(settings, "deployment_mode", "enterprise")
    body = client.get("/api/v1/meta").json()
    assert body["deployment_mode"] == "enterprise"
    assert body["limits"] is None


def test_telegram_token_masked_and_encrypted(client, auth_headers, db_session_factory):
    from sqlalchemy import select

    from app.core.security import decrypt_secret
    from app.models import TelegramIntegration

    token = "123456:AAAbbbCCCdddEEE"
    response = client.post(
        "/api/v1/telegram/connect",
        json={"bot_token": token, "chat_id": "42", "alert_scopes": ["down"]},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert token not in str(body)
    assert body["bot_token_masked"] == "1234...dEEE"

    with db_session_factory() as db:
        integration = db.scalar(select(TelegramIntegration))
        assert integration.bot_token_secret != token
        assert decrypt_secret(integration.bot_token_secret) == token


def test_telegram_read_integration(client, auth_headers):
    body = client.get("/api/v1/telegram", headers=auth_headers).json()
    assert body == {"connected": False, "chat_id": None, "alert_scopes": [], "bot_token_masked": None}

    token = "123456:AAAbbbCCCdddEEE"
    client.post(
        "/api/v1/telegram/connect",
        json={"bot_token": token, "chat_id": "42", "alert_scopes": ["down"]},
        headers=auth_headers,
    )

    body = client.get("/api/v1/telegram", headers=auth_headers).json()
    assert body["connected"] is True
    assert body["chat_id"] == "42"
    assert body["alert_scopes"] == ["down"]
    assert body["bot_token_masked"] == "1234...dEEE"
    assert token not in str(body)


def test_user_isolation(client):
    user_a = {"email": "a@example.com", "password": "password123"}
    user_b = {"email": "b@example.com", "password": "password123"}
    client.post("/api/v1/auth/register", json=user_a)
    client.post("/api/v1/auth/register", json=user_b)
    headers_a = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json=user_a).json()['access_token']}"}
    headers_b = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json=user_b).json()['access_token']}"}

    created = client.post(
        "/api/v1/monitors",
        json={"id": "site-a", "type": "http", "url": "https://example.com", "interval": 60},
        headers=headers_a,
    )
    assert created.status_code == 201

    assert client.get("/api/v1/monitors", headers=headers_b).json() == []
    assert client.get("/api/v1/monitors/site-a", headers=headers_b).status_code == 404
    assert client.put("/api/v1/monitors/site-a", json={"enabled": False}, headers=headers_b).status_code == 404
    assert client.delete("/api/v1/monitors/site-a", headers=headers_b).status_code == 404
    assert client.get("/api/v1/config/versions", headers=headers_b).json() == []
    assert client.get("/api/v1/history", headers=headers_b).json() == []

    # монитор user A не пострадал
    assert client.get("/api/v1/monitors/site-a", headers=headers_a).status_code == 200
