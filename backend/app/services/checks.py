import time
from typing import Any, Protocol

import httpx

from app.schemas import CheckTask


class BrowserRunner(Protocol):
    async def run(self, task: CheckTask) -> dict[str, Any]: ...


async def run_http_check(task: CheckTask) -> dict[str, Any]:
    if not task.url:
        return {"status": "down", "response_time_ms": None, "error": "missing url", "details": {}}
    expected = task.config.get("expected") or {}
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=task.timeout_seconds, follow_redirects=True) as client:
            response = await client.get(task.url)
        elapsed = int((time.perf_counter() - started) * 1000)
        expected_status = expected.get("status")
        body_contains = expected.get("body_contains")
        if expected_status and response.status_code != expected_status:
            return {
                "status": "down",
                "response_time_ms": elapsed,
                "error": f"expected status {expected_status}, got {response.status_code}",
                "details": {"status_code": response.status_code},
            }
        if body_contains and body_contains not in response.text:
            return {
                "status": "degraded",
                "response_time_ms": elapsed,
                "error": "expected body text not found",
                "details": {"status_code": response.status_code},
            }
        return {
            "status": "up",
            "response_time_ms": elapsed,
            "error": None,
            "details": {"status_code": response.status_code},
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "down", "response_time_ms": None, "error": str(exc), "details": {}}


class PlaywrightBrowserRunner:
    async def run(self, task: CheckTask) -> dict[str, Any]:
        from playwright.async_api import async_playwright

        steps = task.config.get("steps") or []
        started = time.perf_counter()
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                page.set_default_timeout(task.timeout_seconds * 1000)
                for step in steps:
                    action = step.get("action")
                    if action == "goto":
                        await page.goto(step["url"])
                    elif action == "click":
                        await page.click(step["selector"])
                    elif action == "type":
                        await page.fill(step["selector"], step.get("value") or step.get("text") or "")
                    elif action == "assert_text":
                        text = step["text"]
                        content = await page.content()
                        if text not in content:
                            raise AssertionError(f"text not found: {text}")
                    else:
                        raise ValueError(f"unsupported browser action: {action}")
                await browser.close()
            return {"status": "up", "response_time_ms": int((time.perf_counter() - started) * 1000), "error": None, "details": {"steps": len(steps)}}
        except Exception as exc:  # noqa: BLE001
            return {"status": "down", "response_time_ms": None, "error": str(exc), "details": {"steps": len(steps)}}


async def run_browser_check(task: CheckTask, runner: BrowserRunner | None = None) -> dict[str, Any]:
    runner = runner or PlaywrightBrowserRunner()
    return await runner.run(task)
