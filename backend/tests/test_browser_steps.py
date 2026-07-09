import pytest

from app.schemas import CheckTask
from app.services.checks import (
    PlaywrightBrowserRunner,
    StepFailure,
    execute_steps,
    resolve_env_placeholders,
)
from app.services.config_sync import dump_config, parse_config


# --- resolve_env_placeholders ---


def test_resolve_env_placeholders_substitutes(monkeypatch):
    monkeypatch.setenv("MONITOR_PASSWORD", "s3cret")
    step = {"action": "type", "selector": "#password", "value": "${MONITOR_PASSWORD}"}
    resolved = resolve_env_placeholders(step)
    assert resolved["value"] == "s3cret"
    # исходный шаг не мутируется
    assert step["value"] == "${MONITOR_PASSWORD}"


def test_resolve_env_placeholders_multiple_vars_in_one_string(monkeypatch):
    monkeypatch.setenv("HOST", "example.com")
    monkeypatch.setenv("PATH_PART", "login")
    step = {"action": "goto", "url": "https://${HOST}/${PATH_PART}"}
    assert resolve_env_placeholders(step)["url"] == "https://example.com/login"


def test_resolve_env_placeholders_missing_var(monkeypatch):
    monkeypatch.delenv("MISSING_VAR", raising=False)
    with pytest.raises(ValueError, match="environment variable 'MISSING_VAR' is not set"):
        resolve_env_placeholders({"action": "type", "selector": "#x", "value": "${MISSING_VAR}"})


# --- execute_steps с FakePage ---


class FakeLocator:
    def __init__(self, text):
        self._text = text

    async def inner_text(self):
        return self._text


class FakePage:
    def __init__(self, content_text="", inner_texts=None, url="https://example.com/"):
        self.calls = []
        self.url = url
        self._content = content_text
        self._inner_texts = inner_texts or {}

    def set_default_timeout(self, ms):
        self.calls.append(("set_default_timeout", ms))

    async def goto(self, url):
        self.calls.append(("goto", url))

    async def click(self, selector):
        self.calls.append(("click", selector))

    async def fill(self, selector, value):
        self.calls.append(("fill", selector, value))

    async def wait_for_selector(self, selector, state=None):
        self.calls.append(("wait_for_selector", selector, state))

    def locator(self, selector):
        self.calls.append(("locator", selector))
        return FakeLocator(self._inner_texts.get(selector, ""))

    async def content(self):
        self.calls.append(("content",))
        return self._content


@pytest.mark.asyncio
async def test_execute_steps_happy_path_all_actions():
    page = FakePage(content_text="Welcome back", inner_texts={"h1": "Dashboard"}, url="https://example.com/dashboard")
    steps = [
        {"action": "goto", "url": "https://example.com/login"},
        {"action": "type", "selector": "#user", "value": "admin"},
        {"action": "click", "selector": "button[type=submit]"},
        {"action": "wait_for", "selector": "h1"},
        {"action": "assert_text", "selector": "h1", "text": "Dashboard"},
        {"action": "assert_url", "contains": "/dashboard"},
    ]
    await execute_steps(page, steps)
    assert page.calls == [
        ("goto", "https://example.com/login"),
        ("fill", "#user", "admin"),
        ("click", "button[type=submit]"),
        ("wait_for_selector", "h1", "visible"),
        ("locator", "h1"),
    ]


@pytest.mark.asyncio
async def test_assert_text_selector_vs_whole_page():
    page = FakePage(content_text="full page body", inner_texts={".alert": "error text"})

    # без селектора — по всей странице
    await execute_steps(page, [{"action": "assert_text", "text": "full page"}])
    assert ("content",) in page.calls

    # с селектором — по inner_text элемента
    await execute_steps(page, [{"action": "assert_text", "selector": ".alert", "text": "error"}])
    assert ("locator", ".alert") in page.calls

    # текст элемента не совпал — падение
    with pytest.raises(StepFailure, match="text not found: missing"):
        await execute_steps(page, [{"action": "assert_text", "selector": ".alert", "text": "missing"}])


@pytest.mark.asyncio
async def test_assert_url_failure_message():
    page = FakePage(url="https://example.com/login")
    with pytest.raises(StepFailure) as excinfo:
        await execute_steps(page, [{"action": "assert_url", "contains": "dashboard"}])
    assert str(excinfo.value) == "step 1 (assert_url): url does not contain 'dashboard': https://example.com/login"


@pytest.mark.asyncio
async def test_execute_steps_unknown_action():
    with pytest.raises(StepFailure, match="unsupported browser action: hover"):
        await execute_steps(FakePage(), [{"action": "hover", "selector": "#x"}])


# --- формат результата PlaywrightBrowserRunner (без реального Chromium) ---


class FakeBrowser:
    def __init__(self, page):
        self._page = page
        self.closed = False

    async def new_page(self):
        return self._page

    async def close(self):
        self.closed = True


class FakeChromium:
    def __init__(self, browser):
        self._browser = browser

    async def launch(self, headless=True):
        return self._browser


class FakePlaywright:
    def __init__(self, browser):
        self.chromium = FakeChromium(browser)


def patch_playwright(monkeypatch, browser):
    class FakeContext:
        async def __aenter__(self):
            return FakePlaywright(browser)

        async def __aexit__(self, *exc_info):
            return False

    monkeypatch.setattr("playwright.async_api.async_playwright", lambda: FakeContext())


def make_browser_task(steps):
    return CheckTask(
        task_id="b1",
        monitor_id=1,
        type="browser",
        config={"steps": steps},
        timeout_seconds=30,
        created_at="2026-01-01T00:00:00Z",
        attempt=1,
    )


@pytest.mark.asyncio
async def test_runner_success_details_final_url(monkeypatch):
    page = FakePage(url="https://example.com/dashboard")
    browser = FakeBrowser(page)
    patch_playwright(monkeypatch, browser)

    result = await PlaywrightBrowserRunner().run(
        make_browser_task([{"action": "goto", "url": "https://example.com/login"}, {"action": "assert_url", "contains": "dashboard"}])
    )
    assert result["status"] == "up"
    assert result["error"] is None
    assert isinstance(result["response_time_ms"], int)
    assert result["details"] == {"steps": 2, "final_url": "https://example.com/dashboard"}
    assert browser.closed is True


@pytest.mark.asyncio
async def test_runner_failure_details_failed_step(monkeypatch):
    page = FakePage(url="https://example.com/login")
    browser = FakeBrowser(page)
    patch_playwright(monkeypatch, browser)

    result = await PlaywrightBrowserRunner().run(
        make_browser_task([{"action": "goto", "url": "https://example.com/login"}, {"action": "assert_url", "contains": "dashboard"}])
    )
    assert result["status"] == "down"
    assert result["response_time_ms"] is None
    assert result["error"] == "step 2 (assert_url): url does not contain 'dashboard': https://example.com/login"
    assert result["details"]["steps"] == 2
    assert result["details"]["failed_step"] == {"index": 2, "action": "assert_url", "contains": "dashboard"}
    assert "screenshot" not in result["details"]
    assert browser.closed is True


@pytest.mark.asyncio
async def test_runner_failure_on_unknown_action(monkeypatch):
    page = FakePage()
    browser = FakeBrowser(page)
    patch_playwright(monkeypatch, browser)

    result = await PlaywrightBrowserRunner().run(make_browser_task([{"action": "hover", "selector": "#x"}]))
    assert result["status"] == "down"
    assert result["details"]["failed_step"] == {"index": 1, "action": "hover", "selector": "#x"}


# --- схема: новые действия проходят parse_config и переживают round-trip ---

NEW_ACTIONS_YAML = """
version: 1
monitors:
  - id: login-flow
    type: browser
    interval: 300
    steps:
      - action: goto
        url: https://example.com/login
      - action: wait_for
        selector: "#username"
      - action: type
        selector: "#password"
        value: ${MONITOR_PASSWORD}
      - action: assert_url
        contains: /dashboard
      - action: assert_text
        selector: h1
        text: Welcome
"""


def test_parse_config_accepts_new_actions_and_round_trips():
    doc = parse_config(NEW_ACTIONS_YAML, "yaml")
    steps = doc.monitors[0].steps
    assert [s.action for s in steps] == ["goto", "wait_for", "type", "assert_url", "assert_text"]
    assert steps[3].contains == "/dashboard"
    assert steps[4].selector == "h1"

    restored = parse_config(dump_config(doc, "yaml"), "yaml")
    assert restored.monitors[0].steps == steps


def test_monitor_api_round_trip_stores_new_steps_in_config(client, auth_headers):
    steps = [
        {"action": "goto", "url": "https://example.com/login"},
        {"action": "wait_for", "selector": "#username"},
        {"action": "assert_url", "contains": "/dashboard"},
        {"action": "assert_text", "selector": "h1", "text": "Welcome"},
    ]
    created = client.post(
        "/api/v1/monitors",
        json={"id": "login-flow", "type": "browser", "url": "https://example.com", "interval": 300, "steps": steps},
        headers=auth_headers,
    )
    assert created.status_code == 201

    monitor = client.get("/api/v1/monitors/login-flow", headers=auth_headers).json()
    stored = monitor["config"]["steps"]
    assert stored[1] == {"action": "wait_for", "selector": "#username"}
    assert stored[2] == {"action": "assert_url", "contains": "/dashboard"}
    assert stored[3] == {"action": "assert_text", "selector": "h1", "text": "Welcome"}
