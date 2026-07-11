# Uplynx: развёртывание в продакшен

Гайд рассчитан на один VPS с Ubuntu 22.04/24.04 и доменом. Результат —
работающий сайт на `https://ваш-домен` с автоматическим TLS, бэкапами
и мониторингом здоровья. Время: ~1 час.

## 0. Что понадобится

| Что | Зачем | Рекомендация |
|---|---|---|
| VPS | весь стек в Docker | 2 vCPU, 4 ГБ RAM, 40 ГБ SSD (browser-воркер ест ~1 ГБ) |
| Домен | ссылка для пользователей и ЮKassa | A-запись на IP VPS (и `www`, если нужен) |
| SMTP | верификация email, сброс пароля, email-алерты | любой транзакционный SMTP; без него вход работает, но верификации не будет |
| Хранилище для бэкапов | дампы БД должны жить не на этом же диске | S3-совместимое / другой сервер / хотя бы rclone в облако |

## 1. Подготовка сервера

```bash
# как root
apt update && apt upgrade -y
curl -fsSL https://get.docker.com | sh

# firewall: наружу только SSH и веб
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw enable

# Caddy — TLS-терминатор перед стеком (сертификаты Let's Encrypt сам получает и продлевает)
apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt update && apt install -y caddy
```

`/etc/caddy/Caddyfile` (замените домен):

```
monitoring.example.ru {
    reverse_proxy 127.0.0.1:8080
}
```

`systemctl reload caddy`. Caddy слушает 80/443, внутрь проксирует на 8080 —
туда мы привяжем nginx стека (сам стек наружу ничего не публикует).

## 2. Код и секреты

```bash
# ВАЖНО: -b main — прод живёт только на main (ветка dev — для разработки,
# по умолчанию в репозитории именно она)
git clone -b main https://github.com/Alabaii/uplynx.git /opt/uplynx
cd /opt/uplynx
```

Создайте `.env` в корне (это единственное место с секретами, в git не попадает):

```bash
# --- обязательные ---
ENVIRONMENT=production                 # запрещает дефолтные секреты
DEPLOYMENT_MODE=enterprise             # SaaS-режим: организации, тарифы, гейтинг
JWT_SECRET_KEY=$(openssl rand -hex 32) # выполните и вставьте ЗНАЧЕНИЕ, не команду
SECRET_ENCRYPTION_KEY=                 # python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
POSTGRES_PASSWORD=<случайный>
POSTGRES_APP_PASSWORD=<случайный другой>

# --- сайт ---
HTTP_PORT=127.0.0.1:8080               # nginx стека виден только Caddy, не интернету
APP_BASE_URL=https://monitoring.example.ru
CORS_ORIGINS=https://monitoring.example.ru

# --- админка (/admin) ---
SUPERUSER_EMAILS=you@example.ru

# --- почта ---
SMTP_HOST=smtp.example.ru
SMTP_PORT=587
SMTP_USERNAME=...
SMTP_PASSWORD=...
SMTP_FROM=Uplynx <no-reply@monitoring.example.ru>

# --- web push (по желанию): python3 -m app.tools.vapid в контейнере backend ---
VAPID_PUBLIC_KEY=
VAPID_PRIVATE_KEY=
VAPID_SUBJECT=mailto:you@example.ru

# --- наблюдаемость (по желанию) ---
SENTRY_DSN=
```

Проверка здравого смысла: `ENVIRONMENT=production` с дефолтным
`JWT_SECRET_KEY` — стек откажется стартовать. Это защита, не бага.

## 3. Запуск

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Миграции применяет сервис `scheduler` автоматически. Проверьте:

```bash
docker compose ps                                  # всё running
curl -s https://monitoring.example.ru/health       # {"status":"ok"}
docker compose logs scheduler --tail 5             # heartbeat, без ошибок
```

Зарегистрируйте свой аккаунт с email из `SUPERUSER_EMAILS` — в сайдбаре
появится «Админка»: тарифы, организации, метрики платформы.

## 4. Бэкапы — сразу, не потом

Сервис `backup` уже снимает суточный `pg_dump` в `/opt/uplynx/backups`
(7 свежих). Дампы на том же диске бесполезны при его смерти — настройте
оффсайт-копию, например rclone в любое S3/облако:

```bash
apt install -y rclone && rclone config   # один раз настроить remote
crontab -e:
30 4 * * * rclone sync /opt/uplynx/backups remote:uplynx-backups --max-age 8d
```

Раз в месяц проверяйте восстановимость (не трогает рабочую БД):

```bash
cd /opt/uplynx && sh deploy/restore-check.sh
```

## 5. Внешний мониторинг мониторинга

Сам себя сервис не спасёт. Повесьте бесплатный внешний проб (UptimeRobot
и т.п.) на два URL:

- `https://домен/health` — жив ли API;
- `https://домен/health/scheduler` — отдаёт 503, если шедулер молчит >30 с.

## 6. Обновления

```bash
cd /opt/uplynx && git pull            # сервер на ветке main: pull подтянет только релизы
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Релиз = PR из `dev` в `main` (обе ветки защищены: мерж только с зелёным CI).
Повседневная разработка идёт ветками от `dev` через PR в `dev`.

Миграции применятся сами. Откат кода: `git checkout <тег/коммит>` и та же
команда; БД назад не откатывается — на то бэкапы.

## 7. Чек-лист перед подачей заявки в ЮKassa

- [ ] Сайт открывается по https, сертификат валидный
- [ ] На сайте видны: описание сервиса, тарифы с ценами в рублях,
      порядок оплаты и возврата, оферта, политика ПДн, контакты и статус
      самозанятого (страницы `/pricing`, `/legal/*`, `/contacts`)
- [ ] В текстах оферты/контактов заполнены ФИО, ИНН и email (плейсхолдеры
      `[...]` заменены)
- [ ] Регистрация и вход работают (проверьте с телефона)
- [ ] SMTP работает: письмо верификации доходит
- [ ] Внешний проб на /health настроен
- [ ] rclone-копия бэкапов ушла в облако хотя бы один раз
