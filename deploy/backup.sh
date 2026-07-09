#!/bin/sh
# Периодический pg_dump с ротацией. Работает sidecar-контейнером postgres:16-alpine —
# pg_dump той же мажорной версии, что и сервер. Формат custom (-Fc): восстанавливается
# pg_restore, сжат, переживает перенос между машинами.
# Первый дамп снимается сразу при старте (проверяемость), дальше по интервалу.
# Переменные: PGHOST/PGUSER/PGPASSWORD/PGDATABASE — стандартные для pg_dump;
# BACKUP_INTERVAL_SECONDS (86400), BACKUP_KEEP (7), BACKUP_DIR (/backups).
set -eu

: "${BACKUP_INTERVAL_SECONDS:=86400}"
: "${BACKUP_KEEP:=7}"
: "${BACKUP_DIR:=/backups}"

mkdir -p "$BACKUP_DIR"

while :; do
  stamp=$(date -u +%Y%m%d-%H%M%S)
  target="$BACKUP_DIR/uplynx-$stamp.dump"
  tmp="$target.part"
  # пишем во временный файл: недокачанный дамп никогда не выглядит валидным
  if pg_dump --format=custom --file="$tmp"; then
    mv "$tmp" "$target"
    echo "backup ok: $target ($(du -h "$target" | cut -f1))"
    ls -1t "$BACKUP_DIR"/uplynx-*.dump 2>/dev/null | tail -n +$((BACKUP_KEEP + 1)) | while read -r old; do
      rm -f "$old" && echo "backup rotated out: $old"
    done
  else
    rm -f "$tmp"
    echo "backup FAILED at $stamp" >&2
  fi
  sleep "$BACKUP_INTERVAL_SECONDS"
done
