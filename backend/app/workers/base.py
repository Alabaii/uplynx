import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

import pika
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.security import decrypt_secret
from app.models import CheckResult, Monitor, PushSubscription, TelegramIntegration
from app.schemas import CheckTask
from app.services.alerting import alert_scope_for_result, build_alert_text
from app.services.queue import deserialize_task
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


async def send_status_alert(monitor: Monitor, check_result: CheckResult, previous_status: str | None) -> None:
    if previous_status == check_result.status:
        return
    scope = alert_scope_for_result(previous_status, check_result.status)
    if not scope:
        return
    text = build_alert_text(monitor, check_result, scope)
    try:
        await send_telegram_alert(monitor, scope, text)
    except Exception:  # noqa: BLE001 — push отправляется независимо от Telegram
        logger.exception("failed to send Telegram alert for monitor %s", monitor.id)
    send_push_alerts(monitor, scope, text)


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
        monitor.status = result["status"]
        db.add(check_result)
        db.commit()
    try:
        await send_status_alert(monitor, check_result, previous_status)
    except Exception:  # noqa: BLE001
        logger.exception("failed to send alert for monitor %s", monitor.id)


def consume_forever(queue: str, runner: ResultRunner, reconnect_delay: float = 5.0) -> None:
    params = pika.URLParameters(get_settings().rabbitmq_url)

    def callback(ch, method, _properties, body):  # type: ignore[no-untyped-def]
        try:
            task = deserialize_task(body)
            result = asyncio.run(runner(task))
            asyncio.run(persist_result(task, result))
        except Exception:  # noqa: BLE001
            logger.exception("failed to process message from queue %s", queue)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return
        ch.basic_ack(delivery_tag=method.delivery_tag)

    while True:
        try:
            connection = pika.BlockingConnection(params)
            channel = connection.channel()
            channel.queue_declare(queue=queue, durable=True)
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=queue, on_message_callback=callback)
            logger.info("consuming queue %s", queue)
            channel.start_consuming()
        except pika.exceptions.AMQPError:
            logger.exception("lost connection to RabbitMQ, retrying in %ss", reconnect_delay)
            time.sleep(reconnect_delay)
