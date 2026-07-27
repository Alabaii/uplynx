"""RLS-контекст сессии (app.org_id) держится весь запрос, а не до первого commit.

Политики org_isolation (миграция 0008) при незаданном app.org_id пропускают всё —
это осознанно для воркеров и админки. Значит потеря настройки внутри запроса
арендатора незаметно снимает второй эшелон защиты: эндпоинты вроде создания
монитора коммитят в середине работы (снимок конфига) и продолжают запросы уже
без контекста.

Сами политики живут только в PostgreSQL, поэтому здесь проверяется механика,
которую видно на sqlite: настройка на этом диалекте не выполняется, а на
мутирующих эндпоинтах с внутренним commit ничего не ломается.
"""
from sqlalchemy import select

from app.api.deps import bind_org_to_rls
from app.models import Monitor


def test_binding_is_noop_on_sqlite(db_session_factory):
    """На sqlite set_config нет — вызов обязан молча ничего не делать."""
    with db_session_factory() as db:
        bind_org_to_rls(db, 42)  # без исключения
        db.commit()
        assert db.scalars(select(Monitor)).all() == []


def test_endpoint_with_internal_commit_still_works(client, auth_headers, db_session_factory):
    """Создание монитора коммитит снимок конфига в середине запроса.

    Именно здесь терялся RLS-контекст. Тест фиксирует, что после переустановки
    настройки на каждую транзакцию сам эндпоинт продолжает работать: монитор
    создан, конфиг-версия записана, чтение после commit возвращает данные.
    """
    response = client.post(
        "/api/v1/monitors",
        headers=auth_headers,
        json={"id": "after-commit", "name": "After commit", "type": "http", "url": "https://example.com", "interval": 60},
    )
    assert response.status_code == 201
    assert response.json()["id"] == "after-commit"

    # чтение конфига в отдельном запросе видит снимок, записанный тем же запросом
    config = client.get("/api/v1/config", headers=auth_headers).json()
    assert "after-commit" in config["content"]

    with db_session_factory() as db:
        assert db.scalar(select(Monitor).where(Monitor.slug == "after-commit")) is not None
