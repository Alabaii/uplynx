"""Потребление очереди воркером: конкурентность, ack/nack, prefetch.

Раньше воркер обрабатывал сообщения строго последовательно (pika с
prefetch_count=1): недоступный адрес занимал его на весь check_timeout_seconds,
и в это время не проверялся ни один монитор ни одной организации. Тесты
фиксируют, что медленная проверка больше не блокирует соседние.
"""
import asyncio

import pytest

from app.services.queue import HTTP_QUEUE
from app.workers.base import consume_queue, handle_message


class FakeMessage:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.acked = False
        self.nack_requeue: bool | None = None

    async def ack(self) -> None:
        self.acked = True

    async def nack(self, requeue: bool = True) -> None:
        self.nack_requeue = requeue


class FakeQueue:
    def __init__(self) -> None:
        self.callback = None

    async def consume(self, callback):  # type: ignore[no-untyped-def]
        self.callback = callback
        return "consumer-tag"


class FakeChannel:
    def __init__(self) -> None:
        self.prefetch_count: int | None = None

    async def set_qos(self, prefetch_count: int) -> None:
        self.prefetch_count = prefetch_count


class FakeConnection:
    def __init__(self, channel: FakeChannel) -> None:
        self._channel = channel

    async def channel(self) -> FakeChannel:
        return self._channel

    async def __aenter__(self) -> "FakeConnection":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


@pytest.fixture()
def fake_broker(monkeypatch):
    """Подменяет подключение к RabbitMQ: возвращает (channel, queue) воркера."""
    channel = FakeChannel()
    queue = FakeQueue()

    async def fake_connect(url):  # type: ignore[no-untyped-def]
        return FakeConnection(channel)

    async def fake_declare(_channel, _queue_name):  # type: ignore[no-untyped-def]
        return queue

    monkeypatch.setattr("aio_pika.connect_robust", fake_connect)
    monkeypatch.setattr("app.workers.base.declare_check_queue_async", fake_declare)
    return channel, queue


async def start_consumer(runner, concurrency, broker):
    """Поднимает consume_queue и ждёт, пока воркер подпишется на очередь."""
    channel, queue = broker
    task = asyncio.create_task(consume_queue(HTTP_QUEUE, runner, concurrency))
    for _ in range(100):
        if queue.callback is not None:
            break
        await asyncio.sleep(0)
    assert queue.callback is not None, "воркер не подписался на очередь"
    return task


@pytest.mark.asyncio
async def test_prefetch_equals_concurrency(fake_broker):
    channel, _ = fake_broker

    async def runner(_task):
        return {"status": "up", "response_time_ms": 1, "error": None, "details": {}}

    task = await start_consumer(runner, 7, fake_broker)
    try:
        # prefetch — единственный ограничитель конкурентности: сколько сообщений
        # брокер отдаёт без подтверждения, столько проверок и идёт параллельно
        assert channel.prefetch_count == 7
    finally:
        task.cancel()


@pytest.mark.asyncio
async def test_slow_check_does_not_block_the_next_one(fake_broker, monkeypatch):
    """Зависшая проверка не задерживает следующее сообщение очереди."""
    _, queue = fake_broker
    monkeypatch.setattr("app.workers.base.persist_result", _noop_persist)
    hanging = asyncio.Event()
    finished: list[str] = []

    async def runner(task):
        if task.task_id == "slow":
            await hanging.wait()  # имитируем недоступный адрес
        finished.append(task.task_id)
        return {"status": "up", "response_time_ms": 1, "error": None, "details": {}}

    consumer = await start_consumer(runner, 4, fake_broker)
    try:
        slow, fast = FakeMessage(_body("slow")), FakeMessage(_body("fast"))
        slow_delivery = asyncio.create_task(queue.callback(slow))
        fast_delivery = asyncio.create_task(queue.callback(fast))

        # быстрая проверка завершается, пока медленная всё ещё висит
        await asyncio.wait_for(fast_delivery, timeout=5)
        assert finished == ["fast"]
        assert fast.acked is True
        assert slow.acked is False

        hanging.set()
        await asyncio.wait_for(slow_delivery, timeout=5)
        assert slow.acked is True
    finally:
        consumer.cancel()


@pytest.mark.asyncio
async def test_broken_message_is_dead_lettered(fake_broker):
    _, queue = fake_broker

    async def runner(_task):
        return {"status": "up", "response_time_ms": 1, "error": None, "details": {}}

    consumer = await start_consumer(runner, 2, fake_broker)
    try:
        message = FakeMessage(b"not-json{{{")
        await asyncio.wait_for(queue.callback(message), timeout=5)
        # requeue=False + dead-letter на очереди → сообщение уходит в DLQ,
        # а не крутится в бесконечной переотправке
        assert message.acked is False
        assert message.nack_requeue is False
    finally:
        consumer.cancel()


@pytest.mark.asyncio
async def test_handle_message_reports_failure_without_raising():
    async def failing_runner(_task):
        raise RuntimeError("browser crashed")

    assert await handle_message(HTTP_QUEUE, failing_runner, _body("x")) is False


async def _noop_persist(_task, _result):
    """Проверки конкурентности не касаются БД — запись результата не нужна."""


def _body(task_id: str) -> bytes:
    from app.schemas import CheckTask

    return (
        CheckTask(
            task_id=task_id,
            monitor_id=1,
            type="http",
            url="https://example.com",
            config={},
            timeout_seconds=30,
            created_at="2026-01-01T00:00:00Z",
            attempt=1,
        )
        .model_dump_json()
        .encode()
    )
