"""Отправка в Telegram: базовый адрес Bot API берётся из настройки.

Нужно там, где api.telegram.org недоступен с хоста (закрыт маршрутом
у провайдера) и запросы идут через свой reverse-proxy. Настройка касается
только Telegram — проверки мониторов остаются прямыми.
"""
import asyncio

from app.core.config import get_settings
from app.services import telegram


class _FakeResponse:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code


def _fake_client(captured: dict, status_code: int = 200):
    class FakeClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None):
            captured["url"] = url
            captured["json"] = json
            return _FakeResponse(status_code)

    return FakeClient


def test_default_base_is_official_api(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(telegram.httpx, "AsyncClient", _fake_client(captured))

    assert asyncio.run(telegram.send_telegram_message("123:ABC", "42", "привет")) is True
    assert captured["url"] == "https://api.telegram.org/bot123:ABC/sendMessage"
    assert captured["json"] == {"chat_id": "42", "text": "привет"}


def test_configured_base_is_honored(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(get_settings(), "telegram_api_base", "https://tg.example.com")
    monkeypatch.setattr(telegram.httpx, "AsyncClient", _fake_client(captured))

    assert asyncio.run(telegram.send_telegram_message("123:ABC", "42", "привет")) is True
    assert captured["url"] == "https://tg.example.com/bot123:ABC/sendMessage"


def test_non_200_is_reported_as_failure(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(telegram.httpx, "AsyncClient", _fake_client(captured, status_code=400))

    assert asyncio.run(telegram.send_telegram_message("123:ABC", "42", "привет")) is False


def test_mask_token_keeps_only_edges():
    assert telegram.mask_token("1234567890:ABCDEFG") == "1234...DEFG"
    assert telegram.mask_token("short") == "***"
