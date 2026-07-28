import asyncio
import re
import socket
import ssl
import time
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings
from app.core.ssrf import BlockedTargetError, resolve_public_address, validate_public_url
from app.schemas import CheckTask

ENV_PLACEHOLDER_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")

SECRET_MASK = "***"

# формат notAfter в getpeercert(): 'Jun  1 12:00:00 2027 GMT'
CERT_DATE_FORMAT = "%b %d %H:%M:%S %Y %Z"

# потолок на читаемое тело ответа: монитор могут навести на большой файл,
# и воркер утянул бы его целиком в память
MAX_BODY_BYTES = 2_000_000

# длина цепочки редиректов (httpx по умолчанию 20): каждый хоп — отдельный
# резолв с проверкой, а сайту для нормальной работы столько переходов не нужно
MAX_REDIRECTS = 5


def parse_cert_not_after(not_after: str) -> datetime:
    return datetime.strptime(not_after, CERT_DATE_FORMAT).replace(tzinfo=timezone.utc)


def fetch_ssl_expiry(url: str, timeout: float = 10.0, allow_private: bool = False) -> datetime | None:
    """Срок действия TLS-сертификата https-хоста; None — не https или получить не удалось."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    try:
        # отдельное соединение мимо httpx: подключаемся к проверенному адресу, а имя
        # хоста уходит только в SNI — иначе повторный резолв между проверкой и
        # соединением уводил бы это соединение во внутреннюю сеть
        address = resolve_public_address(url, allow_private=allow_private) or parsed.hostname
        context = ssl.create_default_context()
        with socket.create_connection((address, parsed.port or 443), timeout=timeout) as sock:
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
    async def run(self, task: CheckTask, secrets: dict[str, str]) -> dict[str, Any]: ...


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


async def read_capped_body(response: httpx.Response) -> tuple[str, bool]:
    """Читает тело ответа не больше MAX_BODY_BYTES; возвращает (текст, обрезано ли).

    Без потолка монитор, наведённый на большой файл, забирал бы его целиком
    в память воркера. Для проверки доступности и поиска подстроки начала
    ответа достаточно.
    """
    chunks: list[bytes] = []
    size = 0
    truncated = False
    async for chunk in response.aiter_bytes():
        chunks.append(chunk)
        size += len(chunk)
        if size >= MAX_BODY_BYTES:
            truncated = True
            break
    raw = b"".join(chunks)[:MAX_BODY_BYTES]
    return raw.decode(response.encoding or "utf-8", errors="replace"), truncated


def pin_target(url: str, allow_private: bool) -> tuple[str, str | None]:
    """(URL с проверенным адресом вместо имени, исходное имя хоста).

    Проверить адрес и тут же отдать имя клиенту недостаточно: httpx резолвит его
    заново перед соединением, и хост под контролем арендатора успевает подменить
    ответ DNS на приватный (rebinding). Поэтому в URL подставляется уже
    проверенный адрес, а имя уезжает в заголовке Host и в SNI — сертификат
    проверяется по нему, как при обычном запросе.
    """
    address = resolve_public_address(url, allow_private=allow_private)
    parsed = httpx.URL(url)
    if address is None:  # allow_private: on-prem ходит по именам как раньше
        return url, None
    netloc_host = f"[{address}]" if ":" in address else address
    pinned = parsed.copy_with(host=netloc_host)
    return str(pinned), parsed.host


async def fetch_following_redirects(
    client: httpx.AsyncClient, url: str, allow_private: bool
) -> tuple[httpx.Response, str]:
    """GET с ручной обработкой редиректов: каждый хоп проверяется и пиннится отдельно.

    follow_redirects=True вернул бы обработку редиректов внутрь httpx, где хост
    резолвится заново и пиннинг теряется. Location может увести на приватный
    адрес — поэтому цепочка идёт через ту же проверку, что и исходный URL.
    """
    for _ in range(MAX_REDIRECTS + 1):
        pinned, host = await asyncio.to_thread(pin_target, url, allow_private)
        headers = {"Host": host} if host else None
        extensions = {"sni_hostname": host} if host and httpx.URL(url).scheme == "https" else None
        request = client.build_request("GET", pinned, headers=headers, extensions=extensions)
        response = await client.send(request, stream=True)
        location = response.headers.get("location")
        if response.is_redirect and location:
            await response.aclose()
            url = str(httpx.URL(url).join(location))
            continue
        return response, url
    raise BlockedTargetError(f"too many redirects (more than {MAX_REDIRECTS})")


async def run_http_check(task: CheckTask) -> dict[str, Any]:
    """HTTP-проверка с потолком на время ЦЕЛИКОМ (см. http_check_budget_seconds).

    Таймаут httpx применяется к отдельной операции, а не к запросу целиком, и
    цепочка редиректов получает его заново на каждом хопе — без этого дедлайна
    медленная цель занимает слот воркера неограниченно долго. Симметрично
    бюджету browser-сценария.
    """
    budget = get_settings().http_check_budget_seconds
    try:
        return await asyncio.wait_for(_perform_http_check(task), timeout=budget)
    except asyncio.TimeoutError:
        # to_thread-операции внутри (резолв, снятие сертификата) отменой не
        # прерываются, но обе ограничены своими таймаутами и завершатся сами
        return {
            "status": "down",
            "response_time_ms": None,
            "error": f"check exceeded the {budget}s budget",
            "details": {"check_budget_seconds": budget},
        }


async def _perform_http_check(task: CheckTask) -> dict[str, Any]:
    if not task.url:
        return {"status": "down", "response_time_ms": None, "error": "missing url", "details": {}}
    expected = task.config.get("expected") or {}
    allow_private = get_settings().allow_private_targets

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=task.timeout_seconds, follow_redirects=False) as client:
            response, _ = await fetch_following_redirects(client, task.url, allow_private)
            try:
                body, truncated = await read_capped_body(response)
            finally:
                await response.aclose()
        elapsed = int((time.perf_counter() - started) * 1000)
        check_status, error = classify_http_result(elapsed, response.status_code, body, expected)
        details: dict[str, Any] = {"status_code": response.status_code}
        if truncated:
            # body_contains искали только в прочитанной части — это должно быть видно
            details["body_truncated_at_bytes"] = MAX_BODY_BYTES
        if task.collect_ssl:
            # хост отвечает — заодно снимаем срок сертификата (blocking socket →
            # отдельный поток). Отдельное соединение с полным хендшейком, поэтому
            # публикующая сторона просит об этом не чаще раза в сутки
            ssl_info = ssl_details(
                await asyncio.to_thread(fetch_ssl_expiry, task.url, allow_private=allow_private)
            )
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


def resolve_placeholders(step: dict, secrets: dict[str, str]) -> dict:
    """Подставляет ${NAME} из секретов организации (services/secrets.py).

    Раньше значения брались из os.environ воркера — арендатор мог шагом
    goto на свой домен унести ключи платформы и секреты соседних организаций.
    Теперь доступны только секреты своего воркспейса; неизвестное имя — ошибка,
    а не пустая строка: тест логина не должен «проходить» с пустым паролем.
    """

    def substitute(match: re.Match[str]) -> str:
        name = match.group(1)
        value = secrets.get(name)
        if value is None:
            raise ValueError(f"secret '{name}' is not defined for this workspace")
        return value

    resolved = dict(step)
    for key in ("url", "selector", "text", "value", "contains"):
        if isinstance(resolved.get(key), str):
            resolved[key] = ENV_PLACEHOLDER_RE.sub(substitute, resolved[key])
    return resolved


def redact_secrets(text: str, secrets: dict[str, str]) -> str:
    """Вычищает подставленные значения секретов из текста ошибки.

    Playwright кладёт в сообщение уже подставленный URL/селектор, а текст
    ошибки уходит в check_results.error и виден всей организации в истории.
    """
    for value in secrets.values():
        if value:
            text = text.replace(value, SECRET_MASK)
    return text


class StepFailure(Exception):
    """Падение конкретного шага сценария: хранит индекс и исходный шаг для диагностики."""

    def __init__(self, index: int, step: dict[str, Any], original: Exception, secrets: dict[str, str]) -> None:
        super().__init__(f"step {index} ({step.get('action')}): {redact_secrets(str(original), secrets)}")
        self.index = index
        self.step = step
        self.original = original


def failed_step_details(failure: StepFailure) -> dict[str, Any]:
    details: dict[str, Any] = {"index": failure.index, "action": failure.step.get("action")}
    for key in ("selector", "url", "contains"):
        if failure.step.get(key):
            details[key] = failure.step[key]
    return details


async def execute_steps(page: Any, steps: list[dict[str, Any]], secrets: dict[str, str] | None = None) -> None:
    secrets = secrets or {}
    for index, raw_step in enumerate(steps, start=1):
        try:
            step = resolve_placeholders(raw_step, secrets)
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
            raise StepFailure(index, raw_step, exc, secrets) from exc


class PlaywrightBrowserRunner:
    async def run(self, task: CheckTask, secrets: dict[str, str]) -> dict[str, Any]:
        from playwright.async_api import async_playwright

        steps = task.config.get("steps") or []
        started = time.perf_counter()
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    page = await browser.new_page()
                    page.set_default_timeout(task.timeout_seconds * 1000)
                    budget = get_settings().browser_scenario_timeout_seconds
                    try:
                        # дедлайн на сценарий целиком: set_default_timeout ограничивает
                        # только отдельный шаг, а их в сценарии до MAX_SCENARIO_STEPS
                        await asyncio.wait_for(execute_steps(page, steps, secrets), timeout=budget)
                    except asyncio.TimeoutError:
                        return {
                            "status": "down",
                            "response_time_ms": None,
                            "error": f"scenario exceeded the {budget}s budget",
                            "details": {"steps": len(steps), "scenario_timeout_seconds": budget},
                        }
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
                        # секрет мог стоять в query последнего URL — в историю он не идёт
                        "details": {"steps": len(steps), "final_url": redact_secrets(page.url, secrets)},
                    }
                finally:
                    await browser.close()
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "down",
                "response_time_ms": None,
                "error": redact_secrets(str(exc), secrets),
                "details": {"steps": len(steps)},
            }


async def run_browser_check(
    task: CheckTask, runner: BrowserRunner | None = None, secrets: dict[str, str] | None = None
) -> dict[str, Any]:
    runner = runner or PlaywrightBrowserRunner()
    return await runner.run(task, secrets or {})
