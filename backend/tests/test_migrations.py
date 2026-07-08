import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]


def run_alembic(database_url: str, *args: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": database_url},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def insert_integration(conn: sqlite3.Connection, user_id: int, org_id: int, chat_id: str) -> None:
    conn.execute(
        "INSERT INTO telegram_integrations (user_id, org_id, bot_token_secret, chat_id, alert_scopes, created_at, updated_at) "
        "VALUES (?, ?, 'secret', ?, '[]', '2026-01-01', '2026-01-01')",
        (user_id, org_id, chat_id),
    )


def test_0003_deduplicates_telegram_integrations_per_org(tmp_path):
    db_path = tmp_path / "migration.db"
    database_url = f"sqlite:///{db_path.as_posix()}"

    run_alembic(database_url, "upgrade", "0002_organizations")

    conn = sqlite3.connect(db_path)
    for email in ("a@example.com", "b@example.com"):
        conn.execute(
            "INSERT INTO users (email, hashed_password, is_active, created_at) VALUES (?, 'x', 1, '2026-01-01')",
            (email,),
        )
    org_id = conn.execute("SELECT id FROM organizations WHERE slug = 'default'").fetchone()[0]
    user_ids = [row[0] for row in conn.execute("SELECT id FROM users ORDER BY id").fetchall()]
    # две интеграции одной организации — до 0003 это было возможно (unique был по user_id)
    insert_integration(conn, user_ids[0], org_id, "first")
    insert_integration(conn, user_ids[1], org_id, "last")
    conn.commit()
    conn.close()

    run_alembic(database_url, "upgrade", "head")

    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT chat_id FROM telegram_integrations").fetchall()
    assert rows == [("last",)]  # осталась строка с максимальным id

    # уникальность по org_id теперь на уровне БД
    with pytest.raises(sqlite3.IntegrityError):
        insert_integration(conn, user_ids[0], org_id, "another")
    conn.close()
