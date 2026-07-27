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
# Запуск (идемпотентно, можно повторять):
#   docker compose exec rabbitmq sh /rabbitmq-policies.sh
# либо с хоста:
#   docker compose exec -T rabbitmq rabbitmqctl set_policy ... (см. ниже)
set -e

# 7 суток: за это время сбой либо заметят по метрике, либо он уже не актуален
DLQ_MESSAGE_TTL_MS="${DLQ_MESSAGE_TTL_MS:-604800000}"
# потолок на случай шторма: старые сообщения вытесняются новыми
DLQ_MAX_LENGTH="${DLQ_MAX_LENGTH:-50000}"

rabbitmqctl set_policy dlq-retention '^.*\.dlq$' \
  "{\"message-ttl\":${DLQ_MESSAGE_TTL_MS},\"max-length\":${DLQ_MAX_LENGTH},\"overflow\":\"drop-head\"}" \
  --apply-to queues --priority 1

rabbitmqctl list_policies
