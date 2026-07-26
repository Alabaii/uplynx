import pytest

from app.schemas import CheckTask
from app.services.alerting import alert_scope_for_result
from app.services.checks import classify_http_result
from app.services.config_sync import parse_config
from app.services.queue import deserialize_task, queue_for_type, serialize_task


def test_config_validator_enums():
    doc = parse_config(
        """
version: 1
monitors:
  - id: login
    type: browser
    interval: 300
    steps:
      - action: goto
        url: https://example.com
      - action: assert_text
        text: Dashboard
""",
        "yaml",
    )
    assert doc.monitors[0].type == "browser"
    with pytest.raises(Exception):
        parse_config("version: 1\nmonitors:\n- id: bad\n  type: ftp\n  interval: 60\n", "yaml")


def test_queue_routing_and_serialization():
    task = CheckTask(
        task_id="t1",
        monitor_id=1,
        type="http",
        url="https://example.com",
        config={},
        timeout_seconds=30,
        created_at="2026-01-01T00:00:00Z",
        attempt=1,
    )
    assert queue_for_type("http") == "http_checks.v2"
    restored = deserialize_task(serialize_task(task))
    assert restored.task_id == "t1"


def test_classify_http_result():
    expected = {"status": 200, "body_contains": "ok", "response_time_ms": 500}
    assert classify_http_result(100, 200, "ok", expected) == ("up", None)
    assert classify_http_result(100, 500, "ok", expected) == ("down", "expected status 200, got 500")
    assert classify_http_result(100, 200, "fail", expected) == ("degraded", "expected body text not found")
    assert classify_http_result(900, 200, "ok", expected) == ("degraded", "slow response: 900 ms > 500 ms")
    # приоритет: сначала доступность, потом скорость
    assert classify_http_result(900, 500, "ok", expected) == ("down", "expected status 200, got 500")


def test_classify_http_result_without_threshold():
    # без порога медленный ответ остаётся up
    assert classify_http_result(9000, 200, "ok", {"status": 200}) == ("up", None)


def test_alert_decisions():
    assert alert_scope_for_result("up", "down") == "down"
    assert alert_scope_for_result("down", "up") == "recovered"
    assert alert_scope_for_result("up", "up") is None


def test_validate_jwt_secret():
    from app.core.config import Settings, validate_jwt_secret

    with pytest.raises(RuntimeError):
        validate_jwt_secret(Settings(environment="production", jwt_secret_key="change-me-in-production"))
    validate_jwt_secret(Settings(environment="production", jwt_secret_key="a-strong-unique-secret"))
    validate_jwt_secret(Settings(environment="development", jwt_secret_key="change-me-in-production"))


def test_encrypt_decrypt_secret_round_trip():
    from app.core.security import decrypt_secret, encrypt_secret

    encrypted = encrypt_secret("123456:token")
    assert encrypted != "123456:token"
    assert decrypt_secret(encrypted) == "123456:token"


@pytest.mark.asyncio
async def test_read_capped_body_truncates_large_response():
    from app.services.checks import MAX_BODY_BYTES, read_capped_body

    class FakeResponse:
        encoding = "utf-8"

        async def aiter_bytes(self):
            # «бесконечный» ответ: без потолка воркер утянул бы его целиком
            for _ in range(100):
                yield b"x" * 100_000

    body, truncated = await read_capped_body(FakeResponse())
    assert truncated is True
    assert len(body) == MAX_BODY_BYTES


@pytest.mark.asyncio
async def test_read_capped_body_keeps_small_response_intact():
    from app.services.checks import read_capped_body

    class FakeResponse:
        encoding = "utf-8"

        async def aiter_bytes(self):
            yield b"all good"

    body, truncated = await read_capped_body(FakeResponse())
    assert body == "all good"
    assert truncated is False
