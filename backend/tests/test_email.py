import smtplib

from app.core.config import get_settings
from app.models import User
from app.services.email import email_enabled, send_email


class FakeSMTP:
    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.starttls_called = False
        self.login_args = None
        self.sent = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self, context=None):
        self.starttls_called = True
        self.starttls_context = context

    def login(self, username, password):
        self.login_args = (username, password)

    def send_message(self, message):
        self.sent.append(message)


def configure_smtp(monkeypatch, **overrides):
    settings = get_settings()
    values = {
        "smtp_host": "smtp.test",
        "smtp_port": 2525,
        "smtp_username": "mailer",
        "smtp_password": "secret",
        "smtp_starttls": True,
    }
    values.update(overrides)
    for key, value in values.items():
        monkeypatch.setattr(settings, key, value)


def install_fake_smtp(monkeypatch, cls=FakeSMTP):
    created = []

    def factory(host, port, timeout=None):
        instance = cls(host, port, timeout=timeout)
        created.append(instance)
        return instance

    monkeypatch.setattr(smtplib, "SMTP", factory)
    return created


def test_email_disabled_without_host(monkeypatch):
    monkeypatch.setattr(get_settings(), "smtp_host", None)
    assert email_enabled() is False
    assert send_email("user@example.com", "Subject", "Body") is False


def test_send_email_uses_starttls_login_and_send(monkeypatch):
    configure_smtp(monkeypatch)
    created = install_fake_smtp(monkeypatch)

    assert email_enabled() is True
    assert send_email("user@example.com", "Hello", "Body text") is True

    smtp = created[0]
    assert (smtp.host, smtp.port) == ("smtp.test", 2525)
    assert smtp.starttls_called is True
    assert smtp.login_args == ("mailer", "secret")
    message = smtp.sent[0]
    assert message["To"] == "user@example.com"
    assert message["From"] == get_settings().smtp_from
    assert message["Subject"] == "Hello"
    assert "Body text" in message.get_content()


def test_send_email_without_starttls_and_login(monkeypatch):
    configure_smtp(monkeypatch, smtp_starttls=False, smtp_username=None)
    created = install_fake_smtp(monkeypatch)

    assert send_email("user@example.com", "Hello", "Body") is True
    smtp = created[0]
    assert smtp.starttls_called is False
    assert smtp.login_args is None


def test_send_email_returns_false_on_smtp_error(monkeypatch):
    configure_smtp(monkeypatch)

    class FailingSMTP(FakeSMTP):
        def send_message(self, message):
            raise smtplib.SMTPException("boom")

    install_fake_smtp(monkeypatch, cls=FailingSMTP)
    assert send_email("user@example.com", "Hello", "Body") is False


def test_meta_reports_email_enabled(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", None)
    assert client.get("/api/v1/meta").json()["email_enabled"] is False

    monkeypatch.setattr(settings, "smtp_host", "smtp.test")
    assert client.get("/api/v1/meta").json()["email_enabled"] is True


def register_and_login(client, email):
    payload = {"email": email, "password": "password123"}
    client.post("/api/v1/auth/register", json=payload)
    token = client.post("/api/v1/auth/login", json=payload).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_owner_updates_alert_emails_member_cannot(client):
    owner = register_and_login(client, "owner@example.com")
    member = register_and_login(client, "member@example.com")

    updated = client.patch(
        "/api/v1/orgs/current",
        json={"alert_emails": ["ops@example.com", "oncall@example.com"]},
        headers=owner,
    )
    assert updated.status_code == 200
    assert updated.json()["alert_emails"] == ["ops@example.com", "oncall@example.com"]

    # адреса читаются любым участником через список организаций
    orgs = client.get("/api/v1/orgs", headers=member).json()
    assert orgs[0]["alert_emails"] == ["ops@example.com", "oncall@example.com"]

    forbidden = client.patch("/api/v1/orgs/current", json={"alert_emails": []}, headers=member)
    assert forbidden.status_code == 403


def test_alert_emails_validation(client):
    owner = register_and_login(client, "owner@example.com")

    too_many = client.patch(
        "/api/v1/orgs/current",
        json={"alert_emails": [f"user{i}@example.com" for i in range(11)]},
        headers=owner,
    )
    assert too_many.status_code == 422

    invalid = client.patch("/api/v1/orgs/current", json={"alert_emails": ["not-an-email"]}, headers=owner)
    assert invalid.status_code == 422


def test_added_member_gets_email_and_failure_does_not_break_add(client, db_session_factory, monkeypatch):
    owner = register_and_login(client, "owner@example.com")
    with db_session_factory() as db:
        db.add(User(email="new@example.com", hashed_password="x"))
        db.add(User(email="second@example.com", hashed_password="x"))
        db.commit()

    sent = []

    def fake_send(to, subject, body):
        sent.append((to, subject, body))
        return True

    monkeypatch.setattr("app.api.v1.endpoints.orgs.send_email", fake_send)
    added = client.post(
        "/api/v1/orgs/current/members", json={"email": "new@example.com", "role": "member"}, headers=owner
    )
    assert added.status_code == 201
    assert sent[0][0] == "new@example.com"
    assert "You were added to" in sent[0][1]

    # сбой почты не ломает добавление участника
    def failing_send(to, subject, body):
        raise RuntimeError("smtp down")

    monkeypatch.setattr("app.api.v1.endpoints.orgs.send_email", failing_send)
    added = client.post(
        "/api/v1/orgs/current/members", json={"email": "second@example.com", "role": "member"}, headers=owner
    )
    assert added.status_code == 201


def test_smtp_connection_is_bounded_by_timeout(monkeypatch):
    """Молчащий SMTP-хост не должен занимать поток из общего пула бесконечно."""
    from app.core.config import get_settings
    from app.services import email as email_service

    monkeypatch.setattr(get_settings(), "smtp_host", "smtp.example.com")
    captured = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self, context=None):
            return None

        def send_message(self, message):
            return None

    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)
    assert email_service.send_email("to@example.com", "s", "b") is True
    assert captured["timeout"] == email_service.SMTP_TIMEOUT_SECONDS
    assert captured["timeout"] > 0
