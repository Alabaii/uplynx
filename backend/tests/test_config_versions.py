"""Список и обрезка версий конфига.

Снимок конфига пишется на каждое изменение монитора, поэтому версии копятся
в обычной работе, а не только при явной загрузке.
"""
from sqlalchemy import func, select

from app.models import ConfigVersion
from app.services.config_sync import MAX_CONFIG_VERSIONS_KEPT


def touch_monitor(client, headers, index):
    client.put("/api/v1/monitors/site", json={"interval": 60 + index}, headers=headers)


def create_monitor(client, headers):
    return client.post(
        "/api/v1/monitors",
        json={"id": "site", "type": "http", "url": "https://example.com", "interval": 60},
        headers=headers,
    )


def test_versions_are_paginated(client, auth_headers):
    assert create_monitor(client, auth_headers).status_code == 201
    for index in range(4):
        touch_monitor(client, auth_headers, index)

    page = client.get("/api/v1/config/versions?limit=2", headers=auth_headers).json()
    assert [row["version"] for row in page] == [5, 4]

    second_page = client.get("/api/v1/config/versions?limit=2&offset=2", headers=auth_headers).json()
    assert [row["version"] for row in second_page] == [3, 2]

    # содержимое версии в списке не отдаётся — за ним идут в GET /config
    assert "content" not in page[0]


def test_versions_limit_is_bounded(client, auth_headers):
    assert client.get("/api/v1/config/versions?limit=500", headers=auth_headers).status_code == 422


def test_old_versions_are_pruned(client, auth_headers, db_session_factory):
    assert create_monitor(client, auth_headers).status_code == 201
    for index in range(MAX_CONFIG_VERSIONS_KEPT + 5):
        touch_monitor(client, auth_headers, index)

    with db_session_factory() as db:
        stored = db.scalar(select(func.count()).select_from(ConfigVersion))
        oldest, newest = db.execute(
            select(func.min(ConfigVersion.version), func.max(ConfigVersion.version))
        ).one()

    assert stored == MAX_CONFIG_VERSIONS_KEPT
    assert newest == MAX_CONFIG_VERSIONS_KEPT + 6
    assert oldest == newest - MAX_CONFIG_VERSIONS_KEPT + 1


def test_rollback_to_a_kept_version_still_works(client, auth_headers):
    assert create_monitor(client, auth_headers).status_code == 201
    touch_monitor(client, auth_headers, 1)

    rolled_back = client.post("/api/v1/config/rollback", json={"version": 1}, headers=auth_headers)
    assert rolled_back.status_code == 200
    assert client.get("/api/v1/monitors/site", headers=auth_headers).json()["interval"] == 60
