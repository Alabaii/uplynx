import logging
import time
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import Monitor
from app.services.queue import RabbitPublisher, task_for_monitor
from app.services.retention import rollup_and_prune

logger = logging.getLogger(__name__)


def publish_due_checks(publisher: RabbitPublisher | None = None) -> int:
    settings = get_settings()
    publisher = publisher or RabbitPublisher()
    now = datetime.now(timezone.utc)
    count = 0
    with SessionLocal() as db:
        monitors = db.scalars(
            select(Monitor)
            .where(Monitor.enabled.is_(True), Monitor.next_run_at <= now)
            .order_by(Monitor.next_run_at)
            .limit(500)
            .with_for_update(skip_locked=True)
        ).all()
        for monitor in monitors:
            task = task_for_monitor(monitor, timeout_seconds=settings.check_timeout_seconds)
            publisher.publish(task)
            monitor.next_run_at = now + timedelta(seconds=monitor.interval)
            count += 1
        db.commit()
    return count


def run_forever() -> None:
    settings = get_settings()
    publisher = RabbitPublisher()
    last_rollup_date: date | None = None
    while True:
        today = datetime.now(timezone.utc).date()
        if today != last_rollup_date:
            last_rollup_date = today
            try:
                with SessionLocal() as db:
                    archived_days, pruned_rows = rollup_and_prune(db)
                logger.info(
                    "retention rollup: archived %s monitor-days, pruned %s raw results", archived_days, pruned_rows
                )
            except Exception:  # noqa: BLE001
                logger.exception("retention rollup failed")
        try:
            publish_due_checks(publisher)
        except Exception:  # noqa: BLE001
            logger.exception("scheduler iteration failed")
        time.sleep(settings.scheduler_poll_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run_forever()
