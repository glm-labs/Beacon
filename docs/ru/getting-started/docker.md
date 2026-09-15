---
title: Установка через Docker
description: Запуск Beacon с помощью Docker Compose
---

# Установка через Docker

Docker Compose — самый быстрый способ запустить Beacon для тестирования, демонстраций и простых self-hosted развёртываний.

Стандартная конфигурация Compose запускает:

```text
beacon             # HTTP API, UI, incoming webhooks
beacon-scheduler   # reminders, escalations, periodic jobs
```

PostgreSQL опционален. SQLite подходит для небольших инсталляций и быстрого старта.

## Архитектура по умолчанию

```text
Docker Compose
├── beacon
│   └── Gunicorn + Flask application
├── beacon-scheduler
│   └── standalone scheduler worker
└── beacon-data
    └── SQLite database volume
```

Путь к SQLite по умолчанию внутри контейнера:

```text
/var/lib/beacon/beacon.db
```

Путь к конфигурации по умолчанию внутри контейнера:

```text
/etc/beacon/beacon.conf
```

Файл конфигурации выбирается через:

```text
BEACON_CONFIG_FILE
```

## Быстрый старт с SQLite

```bash
docker compose up -d --build
```

Откройте UI:

```text
http://SERVER_IP:8080/login
```

Показать логи:

```bash
docker compose logs -f beacon
docker compose logs -f beacon-scheduler
```

## Запуск миграций

Если миграции не запускаются автоматически точкой входа вашего контейнера, выполните:

```bash
docker compose exec beacon python manage.py migrate
```

## Создание первого пользователя-администратора

```bash
docker compose exec beacon \
  python manage.py create-admin \
    --username admin \
    --password 'change-me-123' \
    --email admin@example.com
```

Смените пароль и email перед использованием в продакшене.

## Конфигурация SQLite по умолчанию

Файл:

```text
docker/beacon.docker.conf
```

Пример:

```ini
[main]
log_level = INFO
log_file = /var/log/beacon/beacon.log

[server]
host = 0.0.0.0
port = 8080
public_base_url = http://localhost:8080

[database]
type = sqlite
path = /var/lib/beacon/beacon.db

[sqlite]
wal = true
busy_timeout = 5000

[voice]
provider = stub
providers_dir = /usr/local/lib/beacon/voice_providers
callback_secret = change-me
```

## Вариант с PostgreSQL

Используйте PostgreSQL для:

- более крупных команд;
- высокого объёма алертов;
- нескольких веб-воркеров;
- долгосрочных продакшен-инсталляций.

Запускайте с PostgreSQL, если репозиторий предоставляет override для Compose с PostgreSQL:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.postgres.yml \
  up -d
```

Пример конфигурации PostgreSQL:

```ini
[database]
type = postgresql
host = postgres
port = 5432
name = beacon
user = beacon
password = beacon-change-me
```

## Внешний доступ

При таком отображении портов:

```yaml
ports:
  - "8080:8080"
```

Beacon доступен по адресу:

```text
http://SERVER_IP:8080
```

если файрвол разрешает порт `8080`.

Для продакшена лучше публиковать Beacon через Nginx или HAProxy с HTTPS:

```text
Internet -> Nginx/HAProxy :443 -> Beacon :8080
```

Правильно задайте публичный URL:

```ini
[server]
public_base_url = https://beacon.example.com
```

`public_base_url` используется для генерируемых ссылок и колбэков.

## Пользовательские голосовые провайдеры

Пользовательские голосовые провайдеры можно смонтировать в:

```text
/usr/local/lib/beacon/voice_providers
```

Пример монтирования в Compose:

```yaml
volumes:
  - ./custom_voice_providers:/usr/local/lib/beacon/voice_providers:ro
```

После изменения файлов провайдеров перезапустите контейнеры:

```bash
docker compose restart beacon beacon-scheduler
```
