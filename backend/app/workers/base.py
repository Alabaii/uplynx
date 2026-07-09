import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone

import pika
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.observability import CHECK_PROCESSING_SECONDS, CHECKS_DEAD_LETTERED, CHECKS_PROCESSED
from app.core.security import decrypt_secret
from app.models import CheckResult, Incident, Monitor, Organization, PushSubscription, TelegramIntegration
from app.schemas import CheckTask
from app.services.alerting import (
    SSL_ALERT_THRESHOLDS,
    alert_scope_for_result,
    build_alert_text,
    build_renotify_text,
    build_ssl_alert_text,
    ssl_threshold_to_alert,
)
from app.services.email import email_enabled, send_email
from app.services.incidents import update_incident_for_status_change
from app.services.queue import declare_check_queue, deserialize_task
from app.services.telegram import send_telegram_message
from app.services.webpush import PushSubscriptionGone, push_enabled, send_web_push

logger = logging.getLogger(__name__)

ResultRunner = Callable[[CheckTask], Awaitable[dict]]


async def send_telegram_alert(monitor: Monitor, scope: str, text: str) -> None:
    with SessionLocal() as db:
        integration = db.scalar(
            select(TelegramIntegration).where(TelegramIntegration.org_id == monitor.org_id)
        )
    if not integration or scope not in (integration.alert_scopes or []):
        return
    bot_token = decrypt_secret(integration.bot_token_secret)
    delivered = await send_telegram_message(bot_token, integration.chat_id, text)
    if delivered:
        logger.info("sent %s alert for monitor %s", scope, monitor.slug)
    else:
        logger.warning("Telegram rejected %s alert for monitor %s (check bot token/chat id)", scope, monitor.slug)


def send_push_alerts(monitor: Monitor, scope: str, body: str) -> None:
    if not push_enabled():
        return
    # scope: down/degraded/recovered -> "slug is DOWN/DEGRADED/RECOVERED"
    title = f"{monitor.slug} is {scope.upper()}"
    url = f"/monitors/{monitor.slug}"
    sent = 0
    removed = 0
    with SessionLocal() as db:
        subscriptions = db.scalars(
            select(PushSubscription).where(PushSubscription.org_id == monitor.org_id)
        ).all()
        for subscription in subscriptions:
            try:
                if send_web_push(subscription, title, body, url=url):
                    sent += 1
            except PushSubscriptionGone:
                db.delete(subscription)
                removed += 1
        if removed:
            db.commit()
    if sent or removed:
        logger.info("sent %s push alerts for monitor %s (removed %s dead subscriptions)", sent, monitor.slug, removed)


async def send_email_alerts(monitor: Monitor, scope: str, body: str) -> None:
    if not email_enabled():
        return
    with SessionLocal() as db:
        org = db.get(Organization, monitor.org_id)
        recipients = list(org.alert_emails or []) if org else []
    if not recipients:
        return
    subject = f"[{scope.upper()}] {monitor.name}"
    sent = 0
    for address in recipients:
        # send_email синхронный (smtplib) — не блокируем event loop
        if await asyncio.to_thread(send_email, address, subject, body):
            sent += 1
    if sent:
        logger.info("sent %s email alerts for monitor %s", sent, monitor.slug)


async def broadcast_alert(monitor: Monitor, scope: str, text: str) -> None:
    """Рассылает текст во все каналы; сбой одного канала не блокирует остальные."""
    try:
        await send_telegram_alert(monitor, scope, text)
    except Exception:  # noqa: BLE001 — push отправляется независимо от Telegram
        logger.exception("failed to send Telegram alert for monitor %s", monitor.id)
    send_push_alerts(monitor, scope, text)
    try:
        await send_email_alerts(monitor, scope, text)
    except Exception:  # noqa: BLE001 — email не должен ломать persist_result
        logger.exception("failed to send email alerts for monitor %s", monitor.id)


async def send_status_alert(monitor: Monitor, check_result: CheckResult, previous_status: str | None) -> None:
    if previous_status == check_result.status:
        return
    scope = alert_scope_for_result(previous_status, check_result.status)
    if not scope:
        return
    await broadcast_alert(monitor, scope, build_alert_text(monitor, check_result, scope))


def apply_ssl_state(monitor: Monitor, ssl_info: dict | None) -> str | None:
    """Обновляет ssl-поля монитора; возвращает текст алерта, если пересечён новый порог."""
    if not ssl_info or not ssl_info.get("expires_at") or ssl_info.get("days_left") is None:
        return None
    expires_at = datetime.fromisoformat(ssl_info["expires_at"])
    days_left = int(ssl_info["days_left"])
    monitor.ssl_expires_at = expires_at
    if days_left > max(SSL_ALERT_THRESHOLDS):
        # сертификат обновили — сбрасываем состояние, чтобы алертить в следующем цикле жизни
        monitor.ssl_alerted_days = None
        return None
    threshold = ssl_threshold_to_alert(days_left, monitor.ssl_alerted_days)
    if threshold is None:
        return None
    monitor.ssl_alerted_days = threshold
    return build_ssl_alert_text(monitor, days_left, expires_at)


def renotify_due(incident: Incident, config_json: dict | None, now: datetime) -> bool:
    """Пора ли слать повторный алерт по открытому инциденту (renotify_interval_minutes)."""
    minutes = (config_json or {}).get("renotify_interval_minutes")
    if not minutes:
        return False
    last = incident.last_notified_at or incident.started_at
    if last.tzinfo is None:  # sqlite отдаёт naive datetime
        last = last.replace(tzinfo=timezone.utc)
    return now - last >= timedelta(minutes=minutes)


def resolve_effective_status(db: Session, monitor: Monitor, raw_status: str) -> str:
    """Анти-флаппинг: статус переключается только после N одинаковых результатов подряд.

    Текущий результат уже должен быть в сессии (flush) — он входит в серию.
    """
    if monitor.status == "pending":
        return raw_status  # новый монитор получает мгновенную обратную связь
    if raw_status == monitor.status:
        return monitor.status
    confirmations = (monitor.config_json or {}).get("confirmations", 1)
    if confirmations <= 1:
        return raw_status
    recent = db.scalars(
        select(CheckResult.status)
        .where(CheckResult.monitor_id == monitor.id)
        .order_by(CheckResult.timestamp.desc(), CheckResult.id.desc())
        .limit(confirmations)
    ).all()
    if len(recent) < confirmations or any(status != raw_status for status in recent):
        return monitor.status
    return raw_status


async def persist_result(task: CheckTask, result: dict) -> None:
    with SessionLocal() as db:
        if db.scalar(select(CheckResult).where(CheckResult.task_id == task.task_id)):
            return
        monitor = db.get(Monitor, task.monitor_id)
        if not monitor:
            return
        previous_status = monitor.status
        check_result = CheckResult(
            monitor_id=monitor.id,
            task_id=task.task_id,
            status=result["status"],
            response_time_ms=result.get("response_time_ms"),
            error=result.get("error"),
            details=result.get("details") or {},
            timestamp=datetime.now(timezone.utc),
        )
        db.add(check_result)
        db.flush()  # текущий результат участвует в серии подтверждений
        monitor.status = resolve_effective_status(db, monitor, result["status"])
        ssl_alert_text = apply_ssl_state(monitor, (result.get("details") or {}).get("ssl"))
        renotify_text: str | None = None
        if monitor.status != previous_status:
            # эффективная смена статуса — точка открытия/закрытия инцидента (та же транзакция)
            update_incident_for_status_change(db, monitor, monitor.status, result.get("error"))
        elif monitor.status in ("down", "degraded"):
            incident = db.scalar(
                select(Incident).where(Incident.monitor_id == monitor.id, Incident.status == "open")
            )
            now = datetime.now(timezone.utc)
            if incident is not None and renotify_due(incident, monitor.config_json, now):
                # отметка до отправки: упавшая рассылка не зациклит повторы на каждой проверке
                incident.last_notified_at = now
                started = incident.started_at
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                minutes_down = int((now - started).total_seconds() // 60)
                error = result.get("error") or incident.trigger_error
                renotify_text = build_renotify_text(monitor, monitor.status, error, minutes_down)
        db.commit()
    if ssl_alert_text:
        try:
            await broadcast_alert(monitor, "ssl", ssl_alert_text)
        except Exception:  # noqa: BLE001
            logger.exception("failed to send ssl alert for monitor %s", monitor.id)
    if monitor.status == previous_status:
        if renotify_text:
            try:
                await broadcast_alert(monitor, monitor.status, renotify_text)
            except Exception:  # noqa: BLE001
                logger.exception("failed to send renotify alert for monitor %s", monitor.id)
        return
    try:
        await send_status_alert(monitor, check_result, previous_status)
    except Exception:  # noqa: BLE001
        logger.exception("failed to send alert for monitor %s", monitor.id)


def process_message(queue: str, runner: ResultRunner, body: bytes) -> bool:
    """Обрабатывает одно сообщение очереди; False — сбой, сообщение уйдёт в DLQ."""
    started = time.perf_counter()
    try:
        task = deserialize_task(body)
        result = asyncio.run(runner(task))
        asyncio.run(persist_result(task, result))
    except Exception:  # noqa: BLE001
        logger.exception("failed to process message from queue %s", queue)
        CHECKS_PROCESSED.labels(queue=queue, result="error").inc()
        CHECKS_DEAD_LETTERED.labels(queue=queue).inc()
        return False
    CHECKS_PROCESSED.labels(queue=queue, result=result.get("status", "unknown")).inc()
    CHECK_PROCESSING_SECONDS.labels(queue=queue).observe(time.perf_counter() - started)
    return True


def consume_forever(queue: str, runner: ResultRunner, reconnect_delay: float = 5.0) -> None:
    params = pika.URLParameters(get_settings().rabbitmq_url)

    def callback(ch, method, _properties, body):  # type: ignore[no-untyped-def]
        if process_message(queue, runner, body):
            ch.basic_ack(delivery_tag=method.delivery_tag)
        else:
            # requeue=False + dead-letter на очереди → сообщение уходит в DLQ
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    while True:
        try:
            connection = pika.BlockingConnection(params)
            channel = connection.channel()
            declare_check_queue(channel, queue)
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=queue, on_message_callback=callback)
            logger.info("consuming queue %s", queue)
            channel.start_consuming()
        except pika.exceptions.AMQPError:
            logger.exception("lost connection to RabbitMQ, retrying in %ss", reconnect_delay)
            time.sleep(reconnect_delay)
