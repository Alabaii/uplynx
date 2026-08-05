#!/bin/sh
# Политика хранения для dead-letter-очередей.
#
# Отклонённое воркером сообщение (nack, requeue=False) уходит в *.dlq и лежит там
# вечно: потребителя у этих очередей нет, глубина видна только в метрике
# uplynx_dlq_depth и в обзоре админки. При устойчивом сбое (например, воркер
# падает на каждом сообщении) очередь растёт, пока RabbitMQ не упрётся в память.
#
# Аргументы объявления существующей очереди изменить нельзя (именно поэтому
# рабочие очереди пришлось пересоздавать под именами *.v2), а политика
# применяется к уже живым очередям — поэтому TTL задаётся так.
#
# Запускает сервис rabbitmq-init при каждом старте стека; PUT политики
# идемпотентен. Вручную (например, после правки значений):
#   docker compose run --rm rabbitmq-init
#
# Политика ставится через management API, а не rabbitmqctl: тому нужен erlang
# cookie узла, то есть запуск внутри контейнера брокера.
set -e

RABBITMQ_HOST="${RABBITMQ_HOST:-rabbitmq}"
RABBITMQ_MGMT_PORT="${RABBITMQ_MGMT_PORT:-15672}"
RABBITMQ_USER="${RABBITMQ_USER:-guest}"
RABBITMQ_PASSWORD="${RABBITMQ_PASSWORD:-guest}"
# 7 суток: за это время сбой либо заметят по метрике, либо он уже не актуален
DLQ_MESSAGE_TTL_MS="${DLQ_MESSAGE_TTL_MS:-604800000}"
# потолок на случай шторма: старые сообщения вытесняются новыми
DLQ_MAX_LENGTH="${DLQ_MAX_LENGTH:-50000}"

API="http://${RABBITMQ_HOST}:${RABBITMQ_MGMT_PORT}/api"
AUTH="${RABBITMQ_USER}:${RABBITMQ_PASSWORD}"

# healthcheck брокера (rabbitmq-diagnostics ping) зеленеет раньше, чем поднимается
# management-плагин, поэтому depends_on недостаточно — ждём сам API
attempt=0
until curl -fsS -u "$AUTH" "$API/overview" >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then
    echo "management API брокера не ответил за 60с" >&2
    exit 1
  fi
  sleep 2
done

# %2F — виртуальный хост "/"
curl -fsS -u "$AUTH" -X PUT "$API/policies/%2F/dlq-retention" \
  -H 'content-type: application/json' \
  -d '{"pattern":"^.*\\.dlq$","apply-to":"queues","priority":1,"definition":{"message-ttl":'"${DLQ_MESSAGE_TTL_MS}"',"max-length":'"${DLQ_MAX_LENGTH}"',"overflow":"drop-head"}}'

echo "политика dlq-retention применена (ttl=${DLQ_MESSAGE_TTL_MS}мс, max-length=${DLQ_MAX_LENGTH})"
