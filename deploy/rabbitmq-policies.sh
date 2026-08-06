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
# management-плагин, поэтому depends_on недостаточно — ждём сам API.
# Код ответа разбираем: 401 ожиданием не лечится, и ждать его молча — значит
# минуту спустя сообщить не о той причине. Пароль применяется только при первой
# инициализации тома, поэтому на живом брокере со старым томом RABBITMQ_PASSWORD
# из окружения расходится с тем, что в mnesia — это самый вероятный отказ здесь.
attempt=0
while :; do
  code=$(curl -sS -o /dev/null -w '%{http_code}' -u "$AUTH" "$API/overview" 2>/dev/null || echo 000)
  case "$code" in
    200) break ;;
    401)
      echo "брокер отверг логин ${RABBITMQ_USER}: RABBITMQ_USER/RABBITMQ_PASSWORD не совпадают с учёткой в томе брокера" >&2
      exit 1
      ;;
  esac
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then
    echo "management API брокера не ответил за 60с (последний код: ${code})" >&2
    exit 1
  fi
  sleep 2
done

# %2F — виртуальный хост "/"
curl -fsS -u "$AUTH" -X PUT "$API/policies/%2F/dlq-retention" \
  -H 'content-type: application/json' \
  -d '{"pattern":"^.*\\.dlq$","apply-to":"queues","priority":1,"definition":{"message-ttl":'"${DLQ_MESSAGE_TTL_MS}"',"max-length":'"${DLQ_MAX_LENGTH}"',"overflow":"drop-head"}}'

echo "политика dlq-retention применена (ttl=${DLQ_MESSAGE_TTL_MS}мс, max-length=${DLQ_MAX_LENGTH})"
