# PWA Monitor

Полноценная платформа для мониторинга веб-сайтов с HTTP и Browser проверками, интеграцией с Telegram и конфигурацией через YAML/JSON.

## Обзор

- **Frontend**: React (Vite) PWA с возможностью работы офлайн, дизайн по брендбуку (см. `frontend/DESIGN_SPEC.md`)
- **Backend**: FastAPI с JWT аутентификацией
- **Database**: PostgreSQL с Alembic миграциями
- **Queue**: RabbitMQ для распределения задач
- **Workers**: Отдельные HTTP и Browser (Playwright) воркеры
- **Alerts**: Telegram Bot — уведомления при смене статуса монитора (down / degraded / recovered)

## Режимы развёртывания

Платформа поставляется в двух редакциях, переключаемых переменной `DEPLOYMENT_MODE` (архитектура — в `ENTERPRISE_PLAN.md`):

- `team` (по умолчанию) — одна команда: лимиты 20 пользователей и 100 активных мониторов (настраиваются `TEAM_MAX_USERS` / `TEAM_MAX_MONITORS`).
- `enterprise` — без встроенных лимитов; мультикомандная модель (организации) описана в `ENTERPRISE_PLAN.md` и внедряется поэтапно.

Текущий режим и лимиты отдаёт публичный эндпоинт `GET /api/v1/meta`.

## Переменные окружения

Полный список — в `.env.example`. Ключевые:

| Переменная | Назначение |
|---|---|
| `JWT_SECRET_KEY` | Секрет подписи JWT. В `ENVIRONMENT=production` запуск с дефолтным значением невозможен |
| `SECRET_ENCRYPTION_KEY` | Fernet-ключ шифрования Telegram bot-токенов в БД (иначе деривируется из JWT-секрета) |
| `CORS_ORIGINS` | Разрешённые origins через запятую (по умолчанию `http://localhost:5173`) |
| `ENVIRONMENT` | `development` / `production` |
| `DEPLOYMENT_MODE` | `team` / `enterprise` |
| `SMTP_HOST` | SMTP-сервер для писем; если пуст — email-канал отключён |
| `APP_BASE_URL` | Базовый URL приложения для ссылок в письмах (по умолчанию `http://localhost:5173`) |
| `SUPERUSER_EMAILS` | Email платформенных админов через запятую — доступ к `/admin` (метрики, тарифы, организации); пусто — админ-панель недоступна |

## Email (SMTP)

Email-канал включается переменной `SMTP_HOST` и покрывает три сценария: сброс пароля
(`/forgot-password`), письмо участнику при добавлении в организацию и email-алерты о смене
статуса мониторов (адреса настраивает owner на странице Alerts, до 10).

Переменные: `SMTP_HOST`, `SMTP_PORT` (587), `SMTP_USERNAME`/`SMTP_PASSWORD` (пусто — без
авторизации), `SMTP_FROM`, `SMTP_STARTTLS` (true), `APP_BASE_URL` — полный список в
`.env.example`. Без `SMTP_HOST` фича выключена и это нормально: эндпоинты отвечают как обычно,
письма просто не отправляются (пишется лог), UI честно показывает, что email не настроен.
Для локальной проверки удобен MailHog (`SMTP_HOST=mailhog`, `SMTP_PORT=1025`, `SMTP_STARTTLS=false`).

## Требования

- Docker и Docker Compose
- Node.js 18+ (для локальной разработки фронтенда)
- Python 3.11+ (для локальной разработки бэкенда)

## Быстрый старт

1. Клонируйте репозиторий:
```bash
git clone <repository-url>
cd pwa-monitor
```

2. Создайте файл `.env` на основе `.env.example`:
```bash
copy .env.example .env
# Отредактируйте .env, заменив секретные ключи
```

3. Запустите все сервисы:
```bash
docker-compose up --build
```

4. Доступные сервисы после запуска:
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- RabbitMQ Management: http://localhost:15672 (guest/guest)

## Ручное тестирование

### 1. Проверка работы бэкенда

**Health check:**
```bash
curl http://localhost:8000/health
```

**Readiness check:**
```bash
curl http://localhost:8000/ready
```

### 2. Регистрация и аутентификация

**Регистрация пользователя:**
```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "securepass123"}'
```

**Логин:**
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "securepass123"}'
```

Сохраните полученный JWT токен для дальнейших запросов:
```bash
TOKEN="your-jwt-token-here"
```

### 3. Работа с конфигурацией

**Получить текущую конфигурацию:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/config
```

**Загрузить YAML конфигурацию:**
```bash
curl -X POST http://localhost:8000/api/v1/config \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: text/yaml" \
  --data-binary @config.yaml
```

Пример `config.yaml`:
```yaml
version: 1
monitors:
  - id: homepage
    type: http
    url: https://example.com
    interval: 60
    enabled: true
    confirmations: 3        # анти-флаппинг: статус меняется после 3 одинаковых результатов подряд
    expected:
      status: 200
      response_time_ms: 1500  # ответ медленнее порога -> статус degraded
```

**Скачать конфигурацию:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/config/download \
  -o downloaded-config.yaml
```

**Просмотр версий:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/config/versions
```

**Откат к предыдущей версии:**
```bash
curl -X POST http://localhost:8000/api/v1/config/rollback \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"version": 1}'
```

### 4. Работа с мониторами

**Список всех мониторов:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/monitors
```

**Создать монитор:**
```bash
curl -X POST http://localhost:8000/api/v1/monitors \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "api-health",
    "type": "http",
    "url": "https://api.example.com/health",
    "interval": 30,
    "enabled": true
  }'
```

**Получить детали монитора:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/monitors/{monitor_id}
```

**Обновить монитор:**
```bash
curl -X PUT http://localhost:8000/api/v1/monitors/{monitor_id} \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"interval": 60}'
```

**Удалить (деактивировать) монитор:**
```bash
curl -X DELETE -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/monitors/{monitor_id}
```

### 5. Просмотр истории проверок

**История с фильтрами:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/history?monitor_id=1&status=down&range=24h"
```

Доступные фильтры:
- `monitor_id`: ID монитора
- `status`: up, down, degraded (мониторы без единой проверки имеют статус `pending`)
- `range`: 1h, 24h, 7d, 30d

### 6. Telegram интеграция

**Подключить Telegram бота:**
```bash
curl -X POST http://localhost:8000/api/v1/telegram/connect \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "bot_token": "YOUR_BOT_TOKEN",
    "chat_id": "YOUR_CHAT_ID",
    "alert_scopes": ["down", "degraded", "recovered"]
  }'
```

**Тест Telegram уведомления:**
```bash
curl -X POST http://localhost:8000/api/v1/telegram/test \
  -H "Authorization: Bearer $TOKEN"
```

### 7. Проверка работы воркеров

1. Создайте HTTP монитор с интервалом 60 секунд
2. Дождитесь 1-2 минуты
3. Проверьте историю:
```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/history
```

4. Проверьте логи воркеров:
```bash
docker-compose logs worker-http
```

### 8. Browser проверки

**Создать browser монитор:**
```bash
curl -X POST http://localhost:8000/api/v1/monitors \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "login-flow",
    "type": "browser",
    "interval": 300,
    "steps": [
      {"action": "goto", "url": "https://example.com/login"},
      {"action": "wait_for", "selector": "#username"},
      {"action": "type", "selector": "#username", "text": "test@example.com"},
      {"action": "type", "selector": "#password", "text": "${MONITOR_PASSWORD}"},
      {"action": "click", "selector": "button[type=\"submit\"]"},
      {"action": "assert_url", "contains": "/dashboard"},
      {"action": "assert_text", "selector": "h1", "text": "Welcome"}
    ]
  }'
```

Поддерживаемые действия: `goto`, `click`, `type`, `wait_for` (дождаться появления элемента),
`assert_url` (текущий URL содержит подстроку `contains`), `assert_text` (текст элемента по `selector`
или всей страницы, если `selector` не задан).

Плейсхолдеры вида `${MONITOR_PASSWORD}` подставляются из переменных окружения browser-воркера
в момент выполнения шага — секреты не хранятся в конфиге и не попадают в историю проверок.
Если переменная не задана, проверка падает с ошибкой `environment variable 'MONITOR_PASSWORD' is not set`.
При падении шага в details результата сохраняются номер шага и JPEG-скриншот страницы.

Проверьте логи browser worker:
```bash
docker-compose logs worker-browser
```

### 9. Проверка RabbitMQ

Откройте RabbitMQ Management UI: http://localhost:15672
- Логин: guest
- Пароль: guest

Проверьте:
- Очереди `http_checks` и `browser_checks`
- Количество сообщений
- Подключенные consumers

## Запуск тестов

### Backend тесты

```bash
cd backend
python -m pytest
```

### Frontend e2e (Playwright)

```bash
cd frontend
npm install
npm run e2e
```

Playwright сам поднимает бэкенд (sqlite) и фронтенд — Docker не нужен.

## Структура проекта

```
pwa-monitor/
├── backend/                 # FastAPI backend
│   ├── app/
│   │   ├── api/v1/         # API endpoints
│   │   ├── core/           # Config, database, security
│   │   ├── models.py       # SQLAlchemy модели
│   │   ├── schemas.py      # Pydantic схемы
│   │   ├── services/       # Business logic
│   │   └── workers/        # Scheduler и workers
│   ├── tests/              # Тесты
│   ├── alembic/            # Миграции
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/              # React (Vite) PWA
│   ├── src/app/           # Страницы, компоненты, api-клиент
│   ├── e2e/               # Playwright e2e
│   └── DESIGN_SPEC.md     # Дизайн-спецификация из Figma-брендбука
├── docker-compose.yml     # Docker Compose конфиг
├── .env.example          # Пример env файла
├── ENTERPRISE_PLAN.md    # Архитектура редакций team/enterprise
├── BACKEND_PLAN.md       # Backend план
├── PLAN.md              # Frontend план
├── prd.md               # Product requirements
└── README.md            # Этот файл
```

## Устранение неполадок

### База данных не запускается

Проверьте логи:
```bash
docker-compose logs postgres
```

Очистите volume если нужно:
```bash
docker-compose down -v
docker-compose up --build
```

### RabbitMQ не доступен

Проверьте healthcheck:
```bash
docker-compose exec rabbitmq rabbitmq-diagnostics ping
```

### Воркеры не обрабатывают задачи

1. Проверьте подключение к RabbitMQ:
```bash
docker-compose logs worker-http
```

2. Проверьте очереди в RabbitMQ Management UI

3. Убедитесь, что мониторы включены (`enabled: true`)

### Telegram не отправляет сообщения

1. Проверьте bot token и chat_id
2. Убедитесь, что бот добавлен в чат
3. Проверьте логи backend:
```bash
docker-compose logs backend
```

## Локальная разработка

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Продакшен деплой

Dev-compose поднимает фронтенд vite-dev-сервером — для сервера используйте
продакшен-оверлей: фронтенд собирается в статику и раздаётся nginx-ом с
same-origin прокси `/api` на бэкенд (PWA-фичи — offline и push — работают
только в production-сборке и только по HTTPS).

1. Создайте `.env` из `.env.example` и заполните секреты:
```bash
cp .env.example .env
# Обязательно: JWT_SECRET_KEY (длинная случайная строка),
# SECRET_ENCRYPTION_KEY (Fernet: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"),
# POSTGRES_PASSWORD и POSTGRES_APP_PASSWORD,
# VAPID-ключи для push: python -m app.tools.vapid (из backend/)
```

2. Запустите продакшен-стек:
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```
`ENVIRONMENT=production` включается автоматически (запуск с дефолтным
JWT-секретом невозможен); порты postgres/rabbitmq наружу не публикуются;
приложение доступно на `HTTP_PORT` (по умолчанию 80).

3. TLS: поставьте перед `HTTP_PORT` reverse-proxy с сертификатом — например,
Caddy (`reverse_proxy localhost:80` + автоматический Let's Encrypt) или
nginx + certbot. HTTPS обязателен для установки PWA и push-уведомлений.

## Безопасность

- JWT_SECRET_KEY должен быть длинным случайным строковым значением
- POSTGRES_PASSWORD должен быть уникальным
- Telegram bot tokens никогда не должны коммититься в git
- Всегда используйте HTTPS в продакшене
- Регулярно обновляйте зависимости

### Row-Level Security (защита в глубину)

Миграция 0008 включает PostgreSQL RLS: строки организаций изолируются политиками по `org_id`
(API выставляет `app.org_id` на каждый запрос). **RLS действует только для непривилегированных
ролей** — суперпользователь обходит политики. Поэтому API и воркеры подключаются ролью
`monitor_app` (`POSTGRES_APP_USER`/`POSTGRES_APP_PASSWORD`), а суперпользователь `monitor`
остаётся только для миграций (scheduler).

- Новые инсталляции: роль создаётся автоматически (`deploy/postgres-init.sh` через
  docker-entrypoint-initdb.d).
- Существующие тома: выполните SQL из `deploy/postgres-init.sh` вручную
  (`docker compose exec postgres psql -U monitor -d monitor`), затем перезапустите сервисы.

Проверка: `SET app.org_id = '999'; SELECT COUNT(*) FROM monitors;` под ролью `monitor_app`
должна вернуть 0.

### Аудит действий

Все изменяющие действия (мониторы, конфиг, Telegram, участники, организации) пишутся в
`audit_log` атомарно с самим действием. Просмотр: `GET /api/v1/orgs/current/audit` (роль
admin+) или карточка «Recent activity» на странице Team.

## Лицензия

MIT
