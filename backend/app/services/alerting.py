from datetime import datetime

from app.models import CheckResult, Monitor

# пороги ssl-алертов в днях до истечения сертификата; алерт шлётся один раз на порог
SSL_ALERT_THRESHOLDS = (30, 14, 7, 1)


def ssl_threshold_to_alert(days_left: int, already_alerted_days: int | None) -> int | None:
    """Самый острый пересечённый порог, по которому ещё не алертили; None — алерт не нужен."""
    crossed = [threshold for threshold in SSL_ALERT_THRESHOLDS if days_left <= threshold]
    if not crossed:
        return None
    tightest = min(crossed)
    if already_alerted_days is not None and tightest >= already_alerted_days:
        return None
    return tightest


def build_ssl_alert_text(monitor: Monitor, days_left: int, expires_at: datetime) -> str:
    date = expires_at.date().isoformat()
    if days_left < 0:
        when = f"expired {-days_left} day(s) ago"
    elif days_left == 0:
        when = "expires today"
    else:
        when = f"expires in {days_left} day(s)"
    return f"[ssl] {monitor.name} ({monitor.slug}): TLS certificate {when} ({date})"


def alert_scope_for_result(previous_status: str | None, result_status: str) -> str | None:
    if result_status == "down":
        return "down"
    if result_status == "degraded":
        return "degraded"
    if result_status == "up" and previous_status in {"down", "degraded"}:
        return "recovered"
    return None


def build_alert_text(monitor: Monitor, result: CheckResult, scope: str) -> str:
    return f"[{scope}] {monitor.name} ({monitor.slug}) is {result.status}. Error: {result.error or 'none'}"


def build_renotify_text(monitor: Monitor, effective_status: str, error: str | None, minutes_down: int) -> str:
    return (
        f"[still {effective_status}] {monitor.name} ({monitor.slug}) is still {effective_status} "
        f"for {minutes_down} min. Error: {error or 'none'}"
    )
