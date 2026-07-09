import asyncio
import os
import re
import socket
import ssl
import time
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings
from app.core.ssrf import BlockedTargetError, validate_public_url
from app.schemas import CheckTask

ENV_PLACEHOLDER_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")

# формат notAfter в getpeercert(): 'Jun  1 12:00:00 2027 GMT'
CERT_DATE_FORMAT = "%b %d %H:%M:%S %Y %Z"


def parse_cert_not_after(not_after: str) -> datetime:
    return datetime.strptime(not_after, CERT_DATE_FORMAT).replace(tzinfo=timezone.utc)


def fetch_ssl_expiry(url: str, timeout: float = 10.0) -> datetime | None:
    """Срок действия TLS-сертификата https-хоста; None — не https или получить не удалось."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    try:
        context = ssl.create_default_context()
        with socket.create_connection((parsed.hostname, parsed.port or 443), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=parsed.hostname) as tls:
                cert = tls.getpeercert()
        not_after = (cert or {}).get("notAfter")
        return parse_cert_not_after(not_after) if not_after else None
    except Exception:  # noqa: BLE001 — сбой получения сертификата не должен ломать проверку
        return None


def ssl_details(expires_at: datetime | None) -> dict[str, Any] | None:
    if expires_at is None:
        return None
    days_left = (expires_at - datetime.now(timezone.utc)).days
    return {"expires_at": expires_at.isoformat(), "days_left": days_left}


class BrowserRunner(Protocol):
    async def run(self, task: CheckTask) -> dict[str, Any]: ...


def classify_http_result(elapsed_ms: int, status_code: int, body_text: str, expected: dict[str, Any]) -> tuple[str, str | None]:
    """Чистая классификация HTTP-ответа: сначала доступность (статус, тело), потом скорость."""
    expected_status = expected.get("status")
    if expected_status and status_code != expected_status:
        return "down", f"expected status {expected_status}, got {status_code}"
    body_contains = expected.get("body_contains")
    if body_contains and body_contains not in body_text:
        return "degraded", "expected body text not found"
    threshold = expected.get("response_time_ms")
    if threshold and elapsed_ms > threshold:
        return "degraded", f"slow response: {elapsed_ms} ms > {threshold} ms"
    return "up", None


async def run_http_check(task: CheckTask) -> dict[str, Any]:
    if not task.url:
        return {"status": "down", "response_time_ms": None, "error": "missing url", "details": {}}
    expected = task.config.get("expected") or {}
    allow_private = get_settings().allow_private_targets

    async def guard_request(request: httpx.Request) -> None:
        # хук срабатывает и на исходный запрос, и на каждый редирект: Location
        # может увести на приватный адрес в обход проверки начального URL
        await asyncio.to_thread(validate_public_url, str(request.url), allow_private=allow_private)

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            timeout=task.timeout_seconds,
            follow_redirects=True,
            event_hooks={"request": [guard_request]},
        ) as client:
            response = await client.get(task.url)
        elapsed = int((time.perf_counter() - started) * 1000)
        check_status, error = classify_http_result(elapsed, response.status_code, response.text, expected)
        details: dict[str, Any] = {"status_code": response.status_code}
        # хост отвечает — заодно снимаем срок сертификата (blocking socket → отдельный поток)
        ssl_info = ssl_details(await asyncio.to_thread(fetch_ssl_expiry, task.url))
        if ssl_info:
            details["ssl"] = ssl_info
        return {
            "status": check_status,
            "response_time_ms": elapsed,
            "error": error,
            "details": details,
        }
    except BlockedTargetError as exc:
        return {"status": "down", "response_time_ms": None, "error": str(exc), "details": {"blocked": True}}
    except Exception as exc:  # noqa: BLE001
        return {"status": "down", "response_time_ms": None, "error": str(exc), "details": {}}


def resolve_env_placeholders(step: dict) -> dict:
    """Подставляет плейсхолдеры ${VAR_NAME} из окружения воркера (PRD 5.10)."""

    def substitute(match: re.Match[str]) -> str:
        name = match.group(1)
        value = os.environ.get(name)
        if value is None:
            raise ValueError(f"environment variable '{name}' is not set")
        return value

    resolved = dict(step)
    for key in ("url", "selector", "text", "value", "contains"):
        if isinstance(resolved.get(key), str):
            resolved[key] = ENV_PLACEHOLDER_RE.sub(substitute, resolved[key])
    return resolved


class StepFailure(Exception):
    """Падение конкретного шага сценария: хранит индекс и исходный шаг для диагностики."""

    def __init__(self, index: int, step: dict[str, Any], original: Exception) -> None:
        super().__init__(f"step {index} ({step.get('action')}): {original}")
        self.index = index
        self.step = step
        self.original = original


def failed_step_details(failure: StepFailure) -> dict[str, Any]:
    details: dict[str, Any] = {"index": failure.index, "action": failure.step.get("action")}
    for key in ("selector", "url", "contains"):
        if failure.step.get(key):
            details[key] = failure.step[key]
    return details


async def execute_steps(page: Any, steps: list[dict[str, Any]]) -> None:
    for index, raw_step in enumerate(steps, start=1):
        try:
            step = resolve_env_placeholders(raw_step)
            action = step.get("action")
            if action == "goto":
                # проверяем уже подставленный URL: ${VAR} не даёт валидировать его в API
                await asyncio.to_thread(
                    validate_public_url, step["url"], allow_private=get_settings().allow_private_targets
                )
                await page.goto(step["url"])
            elif action == "click":
                await page.click(step["selector"])
            elif action == "type":
                await page.fill(step["selector"], step.get("value") or step.get("text") or "")
            elif action == "wait_for":
                await page.wait_for_selector(step["selector"], state="visible")
            elif action == "assert_text":
                text = step["text"]
                if step.get("selector"):
                    content = await page.locator(step["selector"]).inner_text()
                else:
                    content = await page.content()
                if text not in content:
                    # в сообщении — сырое значение шага: подставленный секрет не должен утекать в историю
                    raise AssertionError(f"text not found: {raw_step.get('text')}")
            elif action == "assert_url":
                contains = step["contains"]
                if contains not in page.url:
                    raise AssertionError(f"url does not contain '{raw_step.get('contains')}': {page.url}")
            else:
                raise ValueError(f"unsupported browser action: {action}")
        except Exception as exc:  # noqa: BLE001
            raise StepFailure(index, raw_step, exc) from exc


class PlaywrightBrowserRunner:
    async def run(self, task: CheckTask) -> dict[str, Any]:
        from playwright.async_api import async_playwright

        steps = task.config.get("steps") or []
        started = time.perf_counter()
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    page = await browser.new_page()
                    page.set_default_timeout(task.timeout_seconds * 1000)
                    try:
                        await execute_steps(page, steps)
                    except StepFailure as failure:
                        return {
                            "status": "down",
                            "response_time_ms": None,
                            "error": str(failure),
                            "details": {
                                "steps": len(steps),
                                "failed_step": failed_step_details(failure),
                            },
                        }
                    return {
                        "status": "up",
                        "response_time_ms": int((time.perf_counter() - started) * 1000),
                        "error": None,
                        "details": {"steps": len(steps), "final_url": page.url},
                    }
                finally:
                    await browser.close()
        except Exception as exc:  # noqa: BLE001
            return {"status": "down", "response_time_ms": None, "error": str(exc), "details": {"steps": len(steps)}}


async def run_browser_check(task: CheckTask, runner: BrowserRunner | None = None) -> dict[str, Any]:
    runner = runner or PlaywrightBrowserRunner()
    return await runner.run(task)
