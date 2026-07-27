"""Проверки настроек, которые обязаны падать на старте, а не в проде."""
import pytest


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


def test_default_infrastructure_passwords_rejected_in_production():
    """Пароли БД и брокера из docker-compose известны всем, кто видел репозиторий."""
    from app.core.config import Settings, validate_infrastructure_credentials

    compose_defaults = {
        "database_url": "postgresql+psycopg2://monitor_app:monitor_app@postgres:5432/monitor",
        "rabbitmq_url": "amqp://guest:guest@rabbitmq:5672/",
    }
    with pytest.raises(RuntimeError, match="DATABASE_URL uses the well-known default password"):
        validate_infrastructure_credentials(Settings(environment="production", **compose_defaults))

    # dev на дефолтах работает как раньше — только предупреждение
    validate_infrastructure_credentials(Settings(environment="development", **compose_defaults))


def test_superuser_database_password_also_checked():
    """У шедулера свой DATABASE_URL — суперпользователь БД, владелец миграций."""
    from app.core.config import Settings, validate_infrastructure_credentials

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        validate_infrastructure_credentials(
            Settings(
                environment="production",
                database_url="postgresql+psycopg2://monitor:monitor@postgres:5432/monitor",
                rabbitmq_url="amqp://uplynx:strong-broker-pass@rabbitmq:5672/",
            )
        )


def test_own_credentials_pass_in_production():
    from app.core.config import Settings, validate_infrastructure_credentials

    validate_infrastructure_credentials(
        Settings(
            environment="production",
            database_url="postgresql+psycopg2://monitor_app:s3cret-app-pass@postgres:5432/monitor",
            rabbitmq_url="amqp://uplynx:strong-broker-pass@rabbitmq:5672/",
        )
    )


def test_sqlite_url_without_credentials_is_fine():
    """Тесты и self-hosted на sqlite ходят без пароля — проверке нечего смотреть."""
    from app.core.config import Settings, validate_infrastructure_credentials

    validate_infrastructure_credentials(
        Settings(
            environment="production",
            database_url="sqlite:///./monitor.db",
            rabbitmq_url="amqp://uplynx:strong-broker-pass@rabbitmq:5672/",
        )
    )


def test_broker_default_password_rejected_in_production():
    from app.core.config import Settings, validate_infrastructure_credentials

    with pytest.raises(RuntimeError, match="RABBITMQ_URL uses the well-known default password"):
        validate_infrastructure_credentials(
            Settings(
                environment="production",
                database_url="postgresql+psycopg2://monitor_app:s3cret-app-pass@postgres:5432/monitor",
                rabbitmq_url="amqp://guest:guest@rabbitmq:5672/",
            )
        )
