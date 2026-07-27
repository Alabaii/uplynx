import asyncio
import logging

from sqlalchemy import select

from app.core.config import get_settings, validate_infrastructure_credentials
from app.core.database import SessionLocal
from app.core.observability import init_sentry, start_metrics_server
from app.models import Monitor
from app.schemas import CheckTask
from app.services.checks import run_browser_check
from app.services.queue import BROWSER_QUEUE
from app.services.secrets import load_org_secrets
from app.workers.base import consume_forever

logger = logging.getLogger(__name__)

semaphore = asyncio.Semaphore(get_settings().browser_concurrency)


def secrets_for_task(task: CheckTask) -> dict[str, str]:
    """Секреты организации монитора — только если сценарий вообще их использует.

    Значения ходят через БД, а не через очередь: тело сообщения переживает
    воркер в DLQ, и класть туда пароли нельзя. org_id берём из задачи, а для
    задач, опубликованных до этого изменения, — из монитора.
    """
    if "${" not in repr(task.config.get("steps") or []):
        return {}
    with SessionLocal() as db:
        org_id = task.org_id or db.scalar(select(Monitor.org_id).where(Monitor.id == task.monitor_id))
        return load_org_secrets(db, org_id) if org_id is not None else {}


async def limited_browser_check(task: CheckTask) -> dict:
    async with semaphore:
        # чтение из БД синхронное (SQLAlchemy) — не блокируем event loop
        secrets = await asyncio.to_thread(secrets_for_task, task)
        return await run_browser_check(task, secrets=secrets)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    validate_infrastructure_credentials(get_settings())
    init_sentry("worker-browser")
    start_metrics_server()
    consume_forever(BROWSER_QUEUE, limited_browser_check)
