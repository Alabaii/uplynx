import json
from datetime import datetime, timezone
from uuid import uuid4

import pika

from app.core.config import get_settings
from app.models import Monitor
from app.schemas import CheckTask

# суффикс .v2 — очередь пересоздана с dead-letter; у RabbitMQ нельзя добавить
# x-dead-letter-* к уже существующей очереди без её удаления
HTTP_QUEUE = "http_checks.v2"
BROWSER_QUEUE = "browser_checks.v2"
DLX_EXCHANGE = "checks.dlx"
DEAD_LETTER_QUEUES = {HTTP_QUEUE: "http_checks.dlq", BROWSER_QUEUE: "browser_checks.dlq"}


def queue_for_type(monitor_type: str) -> str:
    if monitor_type == "http":
        return HTTP_QUEUE
    if monitor_type == "browser":
        return BROWSER_QUEUE
    raise ValueError(f"Unsupported monitor type: {monitor_type}")


def declare_check_queue(channel: "pika.adapters.blocking_connection.BlockingChannel", queue: str) -> None:
    """Идемпотентно объявляет рабочую очередь с dead-letter и её DLQ.

    Отклонённое воркером (nack, requeue=False) сообщение RabbitMQ автоматически
    перекладывает в DLX → DLQ вместо тихой потери. Вызывается и publisher'ом,
    и consumer'ом — кто первый, тот и создаёт topology.
    """
    dead_queue = DEAD_LETTER_QUEUES[queue]
    channel.exchange_declare(exchange=DLX_EXCHANGE, exchange_type="direct", durable=True)
    channel.queue_declare(queue=dead_queue, durable=True)
    channel.queue_bind(queue=dead_queue, exchange=DLX_EXCHANGE, routing_key=dead_queue)
    channel.queue_declare(
        queue=queue,
        durable=True,
        arguments={"x-dead-letter-exchange": DLX_EXCHANGE, "x-dead-letter-routing-key": dead_queue},
    )


def task_for_monitor(monitor: Monitor, timeout_seconds: int = 30) -> CheckTask:
    return CheckTask(
        task_id=str(uuid4()),
        monitor_id=monitor.id,
        type=monitor.type,  # type: ignore[arg-type]
        url=monitor.url,
        config=monitor.config_json or {},
        timeout_seconds=timeout_seconds,
        created_at=datetime.now(timezone.utc),
        attempt=1,
    )


def serialize_task(task: CheckTask) -> bytes:
    return task.model_dump_json().encode("utf-8")


def deserialize_task(payload: bytes) -> CheckTask:
    return CheckTask.model_validate(json.loads(payload.decode("utf-8")))


class RabbitPublisher:
    def __init__(self, url: str | None = None) -> None:
        self.url = url or get_settings().rabbitmq_url
        self._connection: pika.BlockingConnection | None = None
        self._channel: pika.adapters.blocking_connection.BlockingChannel | None = None

    def _get_channel(self) -> "pika.adapters.blocking_connection.BlockingChannel":
        if self._channel is None or self._channel.is_closed or self._connection is None or self._connection.is_closed:
            self.close()
            self._connection = pika.BlockingConnection(pika.URLParameters(self.url))
            self._channel = self._connection.channel()
        return self._channel

    def close(self) -> None:
        try:
            if self._connection and self._connection.is_open:
                self._connection.close()
        except Exception:  # noqa: BLE001
            pass
        self._connection = None
        self._channel = None

    def _publish(self, queue: str, body: bytes) -> None:
        channel = self._get_channel()
        declare_check_queue(channel, queue)
        channel.basic_publish(
            exchange="",
            routing_key=queue,
            body=body,
            properties=pika.BasicProperties(delivery_mode=2, content_type="application/json"),
        )

    def publish(self, task: CheckTask) -> None:
        queue = queue_for_type(task.type)
        body = serialize_task(task)
        try:
            self._publish(queue, body)
        except pika.exceptions.AMQPError:
            self.close()
            self._publish(queue, body)
