#!/bin/sh
# Создаёт непривилегированную роль приложения. Выполняется автоматически
# при ПЕРВОЙ инициализации тома postgres (docker-entrypoint-initdb.d).
# Без этой роли Row-Level Security декоративен: POSTGRES_USER в официальном
# образе — суперпользователь и обходит политики даже с FORCE.
# Для уже существующих томов выполните SQL ниже вручную (см. README).
set -e

: "${POSTGRES_APP_USER:=monitor_app}"
: "${POSTGRES_APP_PASSWORD:=monitor_app}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
	CREATE ROLE "$POSTGRES_APP_USER" LOGIN PASSWORD '$POSTGRES_APP_PASSWORD' NOSUPERUSER NOCREATEDB NOCREATEROLE;
	GRANT CONNECT ON DATABASE "$POSTGRES_DB" TO "$POSTGRES_APP_USER";
	GRANT USAGE ON SCHEMA public TO "$POSTGRES_APP_USER";
	GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "$POSTGRES_APP_USER";
	GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "$POSTGRES_APP_USER";
	ALTER DEFAULT PRIVILEGES FOR ROLE "$POSTGRES_USER" IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "$POSTGRES_APP_USER";
	ALTER DEFAULT PRIVILEGES FOR ROLE "$POSTGRES_USER" IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO "$POSTGRES_APP_USER";
EOSQL
