import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def email_enabled() -> bool:
    return bool(get_settings().smtp_host)


def send_email(to: str, subject: str, body: str) -> bool:
    """Отправляет plain-text письмо синхронно; в async-коде оборачивать в asyncio.to_thread.

    Ошибки не пробрасываются: письмо — вспомогательный канал и не должно ломать вызывающий код.
    """
    settings = get_settings()
    if not settings.smtp_host:
        logger.info("email disabled; would send %r to %s", subject, to)
        return False
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = subject
    # cte=8bit: quoted-printable разрывает длинные строки мягкими переносами,
    # из-за чего ссылка сброса пароля ломается в части почтовых клиентов
    message.set_content(body, cte="8bit")
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
            if settings.smtp_starttls:
                # без явного контекста smtplib берёт тот, что не проверяет
                # сертификат и имя хоста: логин SMTP и ссылка сброса пароля
                # уходили бы по каналу, который можно перехватить подменой
                smtp.starttls(context=ssl.create_default_context())
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password or "")
            smtp.send_message(message)
    except Exception:  # noqa: BLE001 — любая ошибка SMTP логируется, но не роняет вызывающий код
        logger.exception("failed to send email %r to %s", subject, to)
        return False
    return True
