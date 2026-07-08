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

# миграции применяет scheduler (суперпользователь БД); backend ходит ролью
# monitor_app без DDL-прав — alembic здесь падал бы на CREATE TABLE
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
