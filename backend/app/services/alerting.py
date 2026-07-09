from app.models import CheckResult, Monitor


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
