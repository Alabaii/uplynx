import pytest

from app.schemas import CheckTask
from app.services.alerting import alert_scope_for_result
from app.services.checks import classify_http_result
from app.services.config_sync import parse_config
from app.services.queue import deserialize_task, queue_for_type, serialize_task


def test_config_validator_enums():
    doc = parse_config(
        """
version: 1
monitors:
  - id: login
    type: browser
    interval: 300
    steps:
      - action: goto
        url: https://example.com
      - action: assert_text
        text: Dashboard
""",
        "yaml",
    )
    assert doc.monitors[0].type == "browser"
    with pytest.raises(Exception):
        parse_config("version: 1\nmonitors:\n- id: bad\n  type: ftp\n  interval: 60\n", "yaml")


def test_queue_routing_and_serialization():
    task = CheckTask(
        task_id="t1",
        monitor_id=1,
        type="http",
        url="https://example.com",
        config={},
        timeout_seconds=30,
        created_at="2026-01-01T00:00:00Z",
        attempt=1,
    )
    assert queue_for_type("http") == "http_checks.v2"
    restored = deserialize_task(serialize_task(task))
    assert restored.task_id == "t1"


def test_classify_http_result():
    expected = {"status": 200, "body_contains": "ok", "response_time_ms": 500}
    assert classify_http_result(100, 200, "ok", expected) == ("up", None)
    assert classify_http_result(100, 500, "ok", expected) == ("down", "expected status 200, got 500")
    assert classify_http_result(100, 200, "fail", expected) == ("degraded", "expected body text not found")
    assert classify_http_result(900, 200, "ok", expected) == ("degraded", "slow response: 900 ms > 500 ms")
    # приоритет: сначала доступность, потом скорость
    assert classify_http_result(900, 500, "ok", expected) == ("down", "expected status 200, got 500")


def test_classify_http_result_without_threshold():
    # без порога медленный ответ остаётся up
    assert classify_http_result(9000, 200, "ok", {"status": 200}) == ("up", None)


def test_alert_decisions():
    assert alert_scope_for_result("up", "down") == "down"
    assert alert_scope_for_result("down", "up") == "recovered"
    assert alert_scope_for_result("up", "up") is None


def test_validate_jwt_secret():
    from app.core.config import Settings, validate_jwt_secret

    with pytest.raises(RuntimeError):
        validate_jwt_secret(Settings(environment="production", jwt_secret_key="change-me-in-production"))
    validate_jwt_secret(Settings(environment="production", jwt_secret_key="a-strong-unique-secret"))
    validate_jwt_secret(Settings(environment="development", jwt_secret_key="change-me-in-production"))


def test_validate_secret_encryption_key():
    from cryptography.fernet import Fernet

    from app.core.config import Settings, validate_secret_encryption_key

    valid_key = Fernet.generate_key().decode()

    # в production ключ обязан быть задан явно: иначе он деривируется из
    # JWT-секрета и ротация последнего убивает расшифровку сохранённых секретов
    with pytest.raises(RuntimeError, match="SECRET_ENCRYPTION_KEY is not set"):
        validate_secret_encryption_key(Settings(environment="production", secret_encryption_key=None))
    validate_secret_encryption_key(Settings(environment="production", secret_encryption_key=valid_key))

    # dev/self-hosted живут на деривации — только предупреждение
    validate_secret_encryption_key(Settings(environment="development", secret_encryption_key=None))

    # мусорный ключ ловим на старте, а не на первой расшифровке
    with pytest.raises(RuntimeError, match="not a valid Fernet key"):
        validate_secret_encryption_key(Settings(environment="development", secret_encryption_key="too-short"))


def test_encrypt_decrypt_secret_round_trip():
    from app.core.security import decrypt_secret, encrypt_secret

    encrypted = encrypt_secret("123456:token")
    assert encrypted != "123456:token"
    assert decrypt_secret(encrypted) == "123456:token"


def test_validate_cors_origins():
    from app.core.config import Settings, validate_cors_origins

    explicit = "https://app.example.ru,https://www.app.example.ru"
    validate_cors_origins(Settings(environment="production", cors_origins=explicit))

    # '*' вместе с allow_credentials снимает CORS совсем — в production это отказ
    with pytest.raises(RuntimeError, match="CORS_ORIGINS contains"):
        validate_cors_origins(Settings(environment="production", cors_origins="*"))
    # в dev — только предупреждение
    validate_cors_origins(Settings(environment="development", cors_origins="*"))

    # домен без схемы браузер не сопоставит: запросы молча начали бы блокироваться
    with pytest.raises(RuntimeError, match="must include a scheme"):
        validate_cors_origins(Settings(environment="production", cors_origins="app.example.ru"))


def test_smtp_starttls_verifies_certificate(monkeypatch):
    import ssl as ssl_module

    from app.core.config import get_settings
    from app.services import email as email_service

    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.ru")
    monkeypatch.setattr(settings, "smtp_starttls", True)
    monkeypatch.setattr(settings, "smtp_username", None)

    used = {}

    class FakeSMTP:
        def __init__(self, host, port):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self, context=None):
            used["context"] = context

        def send_message(self, message):
            used["sent"] = True

    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)
    assert email_service.send_email("to@example.ru", "subject", "body") is True

    context = used["context"]
    assert context is not None, "без контекста smtplib не проверяет сертификат"
    assert context.verify_mode == ssl_module.CERT_REQUIRED
    assert context.check_hostname is True
