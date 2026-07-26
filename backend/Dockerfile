# 3.12 — как в CI и dev-venv; НЕ бампать без проверки docker build: greenlet==3.1.1
# (жёсткий пин playwright 1.49) без колёс не компилируется под новые версии Python —
# dependabot-бамп на 3.14 ломал сборку, а CI образ не собирает и этого не ловит
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# процесс не должен идти от root: код и зависимости ему только на чтение,
# а порт 8000 непривилегированный. Пользователь создаётся после COPY, чтобы
# файлы остались принадлежать root — контейнер не сможет переписать сам себя
RUN useradd --system --create-home --uid 10001 appuser
USER appuser

# миграции применяет scheduler (суперпользователь БД); backend ходит ролью
# monitor_app без DDL-прав — alembic здесь падал бы на CREATE TABLE
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
