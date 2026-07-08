# Backend PLAN.md

## Scope

Build a backend implementation for the PRD v1 monitoring platform:

- FastAPI API with health/readiness, JWT auth, config, monitor/history, and Telegram endpoints.
- PostgreSQL persistence through SQLAlchemy 2.x and Alembic migrations.
- RabbitMQ task contract for HTTP and browser checks.
- Scheduler and workers as separate runnable entrypoints.
- Docker Compose one-command startup with backend, frontend, scheduler, workers, RabbitMQ, and PostgreSQL.
- Verification suite covering validators, auth, config sync, API, queue routing, workers, and alert decisions.

## Architecture

```text
frontend -> backend FastAPI -> PostgreSQL
                         -> RabbitMQ queues: http_checks, browser_checks
scheduler -> RabbitMQ
worker-http -> PostgreSQL + alert service
worker-browser -> PostgreSQL + alert service
backend -> Telegram Bot API
```

- Config is the primary source of truth.
- UI/API CRUD changes are converted back into config versions through the same sync service.
- Workers write `CheckResult` idempotently by `task_id`.
- Telegram bot tokens are write-only and never appear in responses or config downloads.

## Phases

- [x] 1. Create backend plan file.
- [x] 2. Backend FastAPI skeleton.
- [x] 3. Database models and migrations.
- [x] 4. JWT authentication.
- [x] 5. Config parser and sync service.
- [x] 6. Monitors and history API.
- [x] 7. RabbitMQ task contract.
- [x] 8. Scheduler service.
- [x] 9. HTTP and browser workers.
- [x] 10. Telegram integration and alerts.
- [x] 11. Docker Compose one-command run.
- [x] 12. Verification suite.

## API Contract

### Health

- `GET /health` -> process health.
- `GET /ready` -> database readiness.

### Auth

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`

### Config

- `GET /api/v1/config`
- `POST /api/v1/config`
- `GET /api/v1/config/download`
- `GET /api/v1/config/versions`
- `POST /api/v1/config/rollback`

### Monitors and results

- `GET /api/v1/monitors`
- `POST /api/v1/monitors`
- `GET /api/v1/monitors/{monitor_id}`
- `PUT /api/v1/monitors/{monitor_id}`
- `DELETE /api/v1/monitors/{monitor_id}` soft-disables the monitor.
- `GET /api/v1/history`

### Telegram

- `POST /api/v1/telegram/connect`
- `POST /api/v1/telegram/test`

## Data Model

- `User`: email, hashed password, active flag.
- `Group`: name.
- `GroupMember`: user/group/role.
- `Monitor`: owner, optional group, slug, type, status, interval, config JSON, enabled, `next_run_at`.
- `CheckResult`: monitor, task id, status, response time, error, timestamp.
- `ConfigVersion`: owner, version number, content, format.
- `TelegramIntegration`: owner, encrypted/write-only bot token, chat id, alert scopes.

## Queue Contract

`CheckTask` JSON:

```json
{
  "task_id": "uuid",
  "monitor_id": 1,
  "type": "http",
  "url": "https://example.com/health",
  "config": {},
  "timeout_seconds": 30,
  "created_at": "2026-01-01T00:00:00Z",
  "attempt": 1
}
```

Routing:

- `http` -> `http_checks`
- `browser` -> `browser_checks`

## Env and Docker

Required env is documented in `.env.example`. Secrets are not committed. Compose starts:

- `postgres`
- `rabbitmq`
- `backend`
- `frontend`
- `scheduler`
- `worker-http`
- `worker-browser`

Backend runs Alembic migrations before API startup.

## Testing Checklist

- [x] Unit: config validator.
- [x] Unit: JWT/password hashing.
- [x] Unit: alert decisions.
- [x] Unit: queue serialization/routing.
- [x] Worker: mocked HTTP/browser adapters.
- [x] Integration: auth + monitor/config/history APIs.
- [x] Smoke documented: compose startup, health, register/login, upload config, list monitors.

## Commands

```bash
cd backend
python -m pytest
uvicorn app.main:app --reload
```

One-command run:

```bash
docker-compose up --build
```

Smoke flow:

1. Open `http://localhost:8000/health`.
2. Register/login through `/api/v1/auth/*`.
3. Upload YAML/JSON to `/api/v1/config`.
4. List `/api/v1/monitors`.
5. Check `/api/v1/history` after workers run.

## Execution Log

- Created `BACKEND_PLAN.md` with architecture, contracts, checks, and phase checklist.
- Added FastAPI skeleton, configuration, routers, and health/readiness endpoints.
- Added SQLAlchemy models and Alembic migration.
- Added auth, config sync, monitor/history, queue, scheduler, workers, Telegram, Compose, and tests.
