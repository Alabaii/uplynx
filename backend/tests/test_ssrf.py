import asyncio

import pytest

from app.core.ssrf import BlockedTargetError, validate_public_url
from app.schemas import CheckTask
from app.services.checks import run_http_check

MONITOR_PAYLOAD = {"id": "site", "type": "http", "url": "https://example.com", "interval": 60}


def fake_getaddrinfo(mapping):
    """socket.getaddrinfo-заглушка: host -> список ip; неизвестный host -> gaierror."""
    import socket

    def _resolver(host, port, *args, **kwargs):
        if host not in mapping:
            raise socket.gaierror(f"unknown host {host}")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port or 0)) for ip in mapping[host]]

    return _resolver


# --- чистая валидация ---------------------------------------------------------------------------


def test_public_literal_ip_allowed():
    validate_public_url("https://93.184.216.34/health", resolve=False)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1",
        "http://10.0.0.5",
        "http://192.168.1.1",
        "http://172.16.0.1",
        "http://169.254.169.254/latest/meta-data/",  # облачные метаданные
        "http://[::1]:8080",
        "http://localhost:5432",
        "http://db.localhost",
        "http://0.0.0.0",
    ],
)
def test_private_targets_blocked(url):
    with pytest.raises(BlockedTargetError):
        validate_public_url(url, resolve=False)


@pytest.mark.parametrize("url", ["ftp://example.com", "file:///etc/passwd", "gopher://x", "://nohost"])
def test_non_http_scheme_blocked(url):
    with pytest.raises(BlockedTargetError):
        validate_public_url(url, resolve=False)


def test_ipv4_mapped_ipv6_loopback_blocked():
    with pytest.raises(BlockedTargetError):
        validate_public_url("http://[::ffff:127.0.0.1]", resolve=False)


def test_allow_private_bypasses_all_checks():
    validate_public_url("http://127.0.0.1", allow_private=True)
    validate_public_url("http://postgres:5432", allow_private=True)


def test_resolve_blocks_hostname_pointing_to_private(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo({"evil.example.com": ["10.0.0.9"]}))
    with pytest.raises(BlockedTargetError):
        validate_public_url("http://evil.example.com", resolve=True)


def test_resolve_allows_hostname_pointing_to_public(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo({"ok.example.com": ["93.184.216.34"]}))
    validate_public_url("http://ok.example.com", resolve=True)


def test_resolve_blocks_if_any_address_is_private(monkeypatch):
    # DNS вернул и публичный, и приватный адрес — блокируем (защита от rebinding)
    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo({"mixed.example.com": ["93.184.216.34", "127.0.0.1"]}))
    with pytest.raises(BlockedTargetError):
        validate_public_url("http://mixed.example.com", resolve=True)


def test_unresolvable_host_blocked(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo({}))
    with pytest.raises(BlockedTargetError):
        validate_public_url("http://nx.invalid", resolve=True)


# --- воркер -------------------------------------------------------------------------------------


def make_task(url):
    return CheckTask(
        task_id="t1",
        monitor_id=1,
        type="http",
        url=url,
        config={},
        timeout_seconds=5,
        created_at="2026-01-01T00:00:00Z",
        attempt=1,
    )


def test_http_worker_blocks_private_literal():
    result = asyncio.run(run_http_check(make_task("http://169.254.169.254/latest/meta-data/")))
    assert result["status"] == "down"
    assert result["details"].get("blocked") is True
    assert "non-public" in result["error"] or "not allowed" in result["error"]


def mock_http_transport(monkeypatch, handler):
    """Подменяет транспорт httpx у воркера, оставляя остальную логику проверки живой."""
    import httpx

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr("app.services.checks.httpx.AsyncClient", client_factory)


def test_http_worker_blocks_redirect_to_private(monkeypatch):
    # первый хост публичный, но 302 уводит на приватный: каждый хоп цепочки
    # проходит ту же проверку, что и исходный URL
    monkeypatch.setattr(
        "socket.getaddrinfo",
        fake_getaddrinfo({"public.example.com": ["93.184.216.34"], "internal.example.com": ["10.0.0.5"]}),
    )

    import httpx

    def handler(request):
        # адрес запроса запиннен на проверенный IP, имя хоста едет в Host
        if request.headers.get("host") == "public.example.com":
            return httpx.Response(302, headers={"Location": "http://internal.example.com/secret"})
        return httpx.Response(200, text="should never reach here")

    mock_http_transport(monkeypatch, handler)

    result = asyncio.run(run_http_check(make_task("http://public.example.com")))
    assert result["status"] == "down"
    assert result["details"].get("blocked") is True


def test_worker_connects_to_the_verified_address(monkeypatch):
    """Соединение идёт на проверенный адрес, имя хоста — в Host и SNI."""
    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo({"shop.example.com": ["93.184.216.34"]}))

    import httpx

    seen = {}

    def handler(request):
        seen["url_host"] = request.url.host
        seen["host_header"] = request.headers.get("host")
        return httpx.Response(200, text="ok")

    mock_http_transport(monkeypatch, handler)
    monkeypatch.setattr("app.services.checks.fetch_ssl_expiry", lambda *a, **kw: None)

    result = asyncio.run(run_http_check(make_task("http://shop.example.com/health")))
    assert result["status"] == "up"
    assert seen["url_host"] == "93.184.216.34"
    assert seen["host_header"] == "shop.example.com"


def test_dns_rebinding_cannot_move_the_connection_inside(monkeypatch):
    """Хост, отдающий приватный адрес ПОСЛЕ проверки, не уводит соединение внутрь.

    Заглушка резолва имитирует rebinding: первый ответ публичный, дальше —
    приватный. Раньше проверка и соединение резолвили имя независимо, поэтому
    запрос уходил на 10.0.0.5; теперь адрес фиксируется в момент проверки.
    """
    import socket as socket_module

    answers = iter([["93.184.216.34"], ["10.0.0.5"], ["10.0.0.5"]])
    last = {"addresses": ["93.184.216.34"]}

    def flipping_resolver(host, port, *args, **kwargs):
        last["addresses"] = next(answers, last["addresses"])
        return [
            (socket_module.AF_INET, socket_module.SOCK_STREAM, 6, "", (ip, port or 0))
            for ip in last["addresses"]
        ]

    monkeypatch.setattr("socket.getaddrinfo", flipping_resolver)

    import httpx

    connected_to = []

    def handler(request):
        connected_to.append(request.url.host)
        return httpx.Response(200, text="ok")

    mock_http_transport(monkeypatch, handler)
    monkeypatch.setattr("app.services.checks.fetch_ssl_expiry", lambda *a, **kw: None)

    result = asyncio.run(run_http_check(make_task("http://rebind.example.com/")))
    assert result["status"] == "up"
    assert connected_to == ["93.184.216.34"]


def test_redirect_loop_is_bounded(monkeypatch):
    """Бесконечная цепочка редиректов обрывается, а не крутится до таймаута."""
    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo({"loop.example.com": ["93.184.216.34"]}))

    import httpx

    hops = []

    def handler(request):
        hops.append(request.url.path)
        return httpx.Response(302, headers={"Location": f"http://loop.example.com{request.url.path}x"})

    mock_http_transport(monkeypatch, handler)

    result = asyncio.run(run_http_check(make_task("http://loop.example.com/")))
    assert result["status"] == "down"
    assert "too many redirects" in result["error"]
    assert len(hops) <= 7  # MAX_REDIRECTS + запрос сверх лимита


# --- API ----------------------------------------------------------------------------------------


def test_api_rejects_private_monitor(client, auth_headers):
    payload = {**MONITOR_PAYLOAD, "url": "http://169.254.169.254/"}
    response = client.post("/api/v1/monitors", json=payload, headers=auth_headers)
    assert response.status_code == 400


def test_api_rejects_localhost_monitor(client, auth_headers):
    payload = {**MONITOR_PAYLOAD, "url": "http://localhost:8000/health"}
    response = client.post("/api/v1/monitors", json=payload, headers=auth_headers)
    assert response.status_code == 400


def test_api_accepts_public_hostname_without_dns(client, auth_headers):
    # resolve=False в API: публичный hostname проходит без сетевого резолва
    response = client.post("/api/v1/monitors", json=MONITOR_PAYLOAD, headers=auth_headers)
    assert response.status_code == 201


def test_api_rejects_placeholder_in_monitor_url(client, auth_headers):
    # ${NAME} подставляется только в шагах browser-сценария: в URL монитора такой
    # адрес и до воркера дошёл бы литералом, и SSRF-проверку обходил
    payload = {**MONITOR_PAYLOAD, "url": "https://${INTERNAL_HOST}/health"}
    response = client.post("/api/v1/monitors", json=payload, headers=auth_headers)
    assert response.status_code == 400
    assert "placeholder" in response.json()["detail"].lower()


def test_api_rejects_placeholder_url_on_update(client, auth_headers):
    assert client.post("/api/v1/monitors", json=MONITOR_PAYLOAD, headers=auth_headers).status_code == 201
    updated = client.put(
        f"/api/v1/monitors/{MONITOR_PAYLOAD['id']}",
        json={"url": "https://${INTERNAL_HOST}/health"},
        headers=auth_headers,
    )
    assert updated.status_code == 400


def test_browser_steps_still_accept_placeholders(client, auth_headers):
    payload = {
        "id": "shop-login",
        "type": "browser",
        "interval": 300,
        "steps": [
            {"action": "goto", "url": "https://shop.example/login?token=${SHOP_TOKEN}"},
            {"action": "type", "selector": "#password", "value": "${SHOP_PASSWORD}"},
        ],
    }
    assert client.post("/api/v1/monitors", json=payload, headers=auth_headers).status_code == 201


def test_api_rejects_private_url_via_config_upload(client, auth_headers):
    config = {
        "content": "version: 1\nmonitors:\n  - id: internal\n    type: http\n    url: http://10.0.0.1/\n    interval: 60\n",
        "format": "yaml",
    }
    response = client.post("/api/v1/config", json=config, headers=auth_headers)
    assert response.status_code == 400
