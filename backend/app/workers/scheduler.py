import logging
import time
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings, validate_infrastructure_credentials
from app.core.database import SessionLocal
from app.core.ratelimit import purge_stale_rate_limits
from app.core.observability import (
    DLQ_DEPTH,
    SCHEDULER_OVERDUE_MONITORS,
    SCHEDULER_PUBLISHED,
    init_sentry,
    start_metrics_server,
)
from app.models import MaintenanceWindow, Monitor, Organization, Plan, SchedulerHeartbeat
from app.services.incidents import resolve_open_incident
from app.services.plans import min_interval_for, plan_gating_active
from app.services.queue import DEAD_LETTER_QUEUES, RabbitPublisher, ssl_refresh_due, task_for_monitor
from app.services.retention import ensure_partitions, purge_expired_tokens, rollup_and_prune

logger = logging.getLogger(__name__)


def update_pipeline_gauges(publisher: RabbitPublisher) -> None:
    """Обновляет gauges тика: отстающие мониторы и глубины DLQ.

    Глубина DLQ берётся из ответа queue_declare (idempotent, тот же durable) —
    без зависимости от management API RabbitMQ.
    """
    settings = get_settings()
    threshold = datetime.now(timezone.utc) - timedelta(seconds=settings.scheduler_heartbeat_stale_seconds)
    with SessionLocal() as db:
        overdue = db.scalar(
            select(func.count())
            .select_from(Monitor)
            .where(Monitor.enabled.is_(True), Monitor.next_run_at < threshold)
        ) or 0
    SCHEDULER_OVERDUE_MONITORS.set(overdue)
    for dead_queue in DEAD_LETTER_QUEUES.values():
        method = publisher.declare_queue(dead_queue)
        DLQ_DEPTH.labels(queue=dead_queue).set(method.method.message_count)


def pause_browser_monitors_if_disabled() -> int:
    """Гасит включённые browser-мониторы, когда сценарии выключены настройкой.

    Просто «не публиковать задачи» здесь мало: монитор остался бы enabled со
    статусом up, и дашборд показывал бы зелёное у сервиса, за которым никто не
    следит. Для продукта про мониторинг это худший вид вранья, поэтому
    состояние приводится в соответствие явно — как при даунгрейде тарифа.

    Открытые инциденты закрываются: проверок не будет, закрыть их иначе некому.
    Обратно мониторы включает владелец — сами они не поднимутся, чтобы
    включение сценариев не запустило разом всё, что копилось.
    """
    if get_settings().browser_monitors_enabled:
        return 0
    with SessionLocal() as db:
        monitors = db.scalars(
            select(Monitor).where(
                Monitor.type == "browser", Monitor.enabled.is_(True), Monitor.archived_at.is_(None)
            )
        ).all()
        for monitor in monitors:
            monitor.enabled = False
            monitor.status = "paused"
            monitor.next_run_at = None
            resolve_open_incident(db, monitor.id)
        if monitors:
            db.commit()
    if monitors:
        logger.warning(
            "browser scenarios are disabled (BROWSER_MONITORS_ENABLED): paused %s monitor(s): %s",
            len(monitors),
            ", ".join(monitor.slug for monitor in monitors),
        )
    return len(monitors)


def write_heartbeat() -> None:
    """Отмечает живость шедулера — читается /health/scheduler для liveness."""
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        beat = db.get(SchedulerHeartbeat, 1)
        if beat is None:
            db.add(SchedulerHeartbeat(id=1, beat_at=now))
        else:
            beat.beat_at = now
        db.commit()


def publish_due_checks(publisher: RabbitPublisher | None = None) -> int:
    settings = get_settings()
    publisher = publisher or RabbitPublisher()
    now = datetime.now(timezone.utc)
    count = 0
    with SessionLocal() as db:
        # fair scheduling: не больше scheduler_org_batch_limit мониторов на организацию за тик;
        # сортировка по rn даёт round-robin между организациями внутри общего лимита
        rank = (
            func.row_number()
            .over(partition_by=Monitor.org_id, order_by=Monitor.next_run_at)
            .label("rn")
        )
        due = select(Monitor.id, Monitor.next_run_at, rank).where(
            Monitor.enabled.is_(True), Monitor.next_run_at <= now
        )
        if not settings.browser_monitors_enabled:
            # Гашение на старте могло не отработать (БД была недоступна — исключение
            # там намеренно проглочено, чтобы шедулер поднялся). Без этого фильтра
            # задача всё равно ушла бы в очередь, воркер вернул бы down, а
            # store_result записал бы его: монитор-то enabled. Итог — ложный
            # инцидент и алерт из-за выключенной нами же фичи
            due = due.where(Monitor.type != "browser")
        ranked = due.subquery()
        due_ids = db.scalars(
            select(ranked.c.id)
            .where(ranked.c.rn <= settings.scheduler_org_batch_limit)
            .order_by(ranked.c.rn, ranked.c.next_run_at)
            .limit(500)
        ).all()
        if not due_ids:
            return 0
        # повторная проверка due-условия: другая реплика могла успеть обработать монитор
        monitors = db.scalars(
            select(Monitor)
            .where(Monitor.id.in_(due_ids), Monitor.enabled.is_(True), Monitor.next_run_at <= now)
            .with_for_update(skip_locked=True)
        ).all()
        maintenance_until = collect_maintenance_ends(db, monitors, now)
        plan_minimums = collect_plan_minimums(db, monitors)
        tasks = []
        for monitor in monitors:
            pause_until = maintenance_until.get(monitor.id)
            if pause_until is not None:
                # активное окно обслуживания: проверку не публикуем,
                # первый запуск — сразу по окончании работ
                monitor.next_run_at = pause_until
                continue
            # срок сертификата снимается не чаще раза в сутки: отметка ставится
            # здесь же, в транзакции сдвига расписания
            collect_ssl = ssl_refresh_due(monitor, now)
            if collect_ssl:
                monitor.ssl_checked_at = now
            tasks.append(
                task_for_monitor(
                    monitor, timeout_seconds=settings.check_timeout_seconds, collect_ssl=collect_ssl
                )
            )
            monitor.next_run_at = now + timedelta(seconds=effective_interval(monitor, plan_minimums))
        # сдвиг расписания фиксируется ДО отправки: если брокер откажет на середине
        # батча, транзакция откатила бы next_run_at уже опубликованным мониторам,
        # и следующий тик проверил бы их повторно. Пропустить тик безопаснее, чем
        # выполнить проверку дважды — при недоступном брокере он всё равно потерян
        db.commit()

    for task in tasks:
        publisher.publish(task)
        count += 1
    if count:
        SCHEDULER_PUBLISHED.inc(count)
    return count


def collect_plan_minimums(db: Session, monitors: list[Monitor]) -> dict[int, Plan]:
    """org_id -> план организации (для клэмпа интервала). Пусто вне enterprise.

    Клэмп на лету делает downgrade честным без мутации настроек мониторов:
    интервал в конфиге пользователя сохраняется и снова действует после апгрейда.
    """
    if not plan_gating_active():
        return {}
    org_ids = {monitor.org_id for monitor in monitors}
    if not org_ids:
        return {}
    rows = db.execute(
        select(Organization.id, Plan)
        .join(Plan, Plan.slug == Organization.plan_slug)
        .where(Organization.id.in_(org_ids))
    ).all()
    return {org_id: plan for org_id, plan in rows}


def effective_interval(monitor: Monitor, plan_minimums: dict[int, Plan]) -> int:
    plan = plan_minimums.get(monitor.org_id)
    if plan is None:
        return monitor.interval
    return max(monitor.interval, min_interval_for(plan, monitor.type))


def collect_maintenance_ends(db: Session, monitors: list[Monitor], now: datetime) -> dict[int, datetime]:
    """monitor.id -> максимальный ends_at активных окон обслуживания монитора.

    Одним запросом забираем активные окна затронутых организаций и раскладываем
    по мониторам в питоне: батч ≤500 строк, окон на организацию единицы — это
    дешевле и переносимее (sqlite/postgres), чем join с агрегацией в SQL.
    """
    org_ids = {monitor.org_id for monitor in monitors}
    if not org_ids:
        return {}
    windows = db.scalars(
        select(MaintenanceWindow).where(
            MaintenanceWindow.org_id.in_(org_ids),
            MaintenanceWindow.starts_at <= now,
            MaintenanceWindow.ends_at > now,
        )
    ).all()
    org_ends: dict[int, datetime] = {}
    monitor_ends: dict[int, datetime] = {}
    for window in windows:
        # sqlite возвращает naive-даты, postgres — aware; приводим к UTC
        ends_at = window.ends_at if window.ends_at.tzinfo else window.ends_at.replace(tzinfo=timezone.utc)
        target, key = (org_ends, window.org_id) if window.monitor_id is None else (monitor_ends, window.monitor_id)
        if key not in target or target[key] < ends_at:
            target[key] = ends_at
    result: dict[int, datetime] = {}
    for monitor in monitors:
        candidates = [ends for ends in (org_ends.get(monitor.org_id), monitor_ends.get(monitor.id)) if ends]
        if candidates:
            result[monitor.id] = max(candidates)
    return result


def run_forever() -> None:
    settings = get_settings()
    publisher = RabbitPublisher()
    last_rollup_date: date | None = None
    try:
        pause_browser_monitors_if_disabled()
    except Exception:  # noqa: BLE001 — недоступная БД на старте не должна ронять шедулер
        logger.exception("failed to pause browser monitors")
    while True:
        today = datetime.now(timezone.utc).date()
        if today != last_rollup_date:
            last_rollup_date = today
            try:
                with SessionLocal() as db:
                    ensure_partitions(db)
                    archived_days, pruned_rows = rollup_and_prune(db)
                    # ключи, которые перестали обращаться, сами себя не вычистят
                    stale_limits = purge_stale_rate_limits(db)
                    # то же с одноразовыми токенами: ротация refresh пишет строку
                    # на каждое продление сессии, удалять их было некому
                    expired_tokens = purge_expired_tokens(db)
                    db.commit()
                logger.info(
                    "retention rollup: archived %s monitor-days, pruned %s raw results, "
                    "%s stale rate-limit rows, %s expired tokens",
                    archived_days,
                    pruned_rows,
                    stale_limits,
                    expired_tokens,
                )
            except Exception:  # noqa: BLE001
                logger.exception("retention rollup failed")
        try:
            publish_due_checks(publisher)
        except Exception:  # noqa: BLE001
            logger.exception("scheduler iteration failed")
        try:
            update_pipeline_gauges(publisher)
        except Exception:  # noqa: BLE001
            logger.exception("failed to update pipeline gauges")
        try:
            # heartbeat после публикации: отражает, что итерация реально дошла до конца
            write_heartbeat()
        except Exception:  # noqa: BLE001
            logger.exception("failed to write scheduler heartbeat")
        time.sleep(settings.scheduler_poll_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # у шедулера свой DATABASE_URL — суперпользователь БД, владелец миграций;
    # его пароль API не видит, поэтому проверяем в каждом процессе отдельно
    validate_infrastructure_credentials(get_settings())
    init_sentry("scheduler")
    start_metrics_server()
    run_forever()
