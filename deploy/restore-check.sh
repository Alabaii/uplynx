#!/bin/sh
# Проверка восстановимости бэкапа: поднимает ВРЕМЕННЫЙ postgres-контейнер,
# восстанавливает дамп и сверяет базовые инварианты (alembic_version, счётчики строк).
# Прод-данные не трогает. Запуск с хоста из корня репозитория:
#   deploy/restore-check.sh [путь-к-дампу]     # по умолчанию — свежайший в ./backups
set -eu

dump="${1:-$(ls -1t backups/uplynx-*.dump 2>/dev/null | head -1)}"
if [ -z "$dump" ] || [ ! -f "$dump" ]; then
  echo "restore-check: дамп не найден (./backups пуст?)" >&2
  exit 1
fi
echo "restore-check: восстанавливаю $dump"

cname="uplynx-restore-check-$$"
docker run -d --name "$cname" -e POSTGRES_PASSWORD=restore-check -e POSTGRES_DB=restore \
  postgres:16-alpine >/dev/null
trap 'docker rm -f "$cname" >/dev/null 2>&1' EXIT

ready=""
for _ in $(seq 1 30); do
  if docker exec "$cname" pg_isready -U postgres -d restore >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
[ -n "$ready" ] || { echo "restore-check: postgres во временном контейнере не поднялся" >&2; exit 1; }

docker cp "$dump" "$cname:/tmp/restore.dump" >/dev/null
# --no-owner/--no-privileges: во временном контейнере нет ролей monitor/monitor_app;
# при реальном восстановлении в прод-стек роли создаёт postgres-init.sh — там флаги не нужны.
# sh -c: путь /tmp/... остаётся контейнерным (Git Bash на Windows переписывает
# аргументы-пути, начинающиеся с /, на хостовые)
docker exec "$cname" sh -c "pg_restore --username=postgres --dbname=restore \
  --no-owner --no-privileges /tmp/restore.dump"

echo "--- инварианты восстановленной базы ---"
docker exec "$cname" psql -U postgres -d restore -t -A -c "
  SELECT 'alembic_version = ' || version_num FROM alembic_version
  UNION ALL SELECT 'users = ' || count(*) FROM users
  UNION ALL SELECT 'organizations = ' || count(*) FROM organizations
  UNION ALL SELECT 'monitors = ' || count(*) FROM monitors
  UNION ALL SELECT 'check_results = ' || count(*) FROM check_results
  UNION ALL SELECT 'incidents = ' || count(*) FROM incidents
  UNION ALL SELECT 'plans = ' || count(*) FROM plans;"

echo "restore-check: OK — дамп восстанавливается"
