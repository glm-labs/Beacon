---
title: Установка с systemd
description: Быстрая установка с сервисами systemd
---

# Установка с systemd

Это руководство описывает классическую установку в Linux с systemd.

Оно запускает два сервиса:

```text
beacon.service        # HTTP API, UI, webhooks
beacon-scheduler.service  # reminders, escalations, periodic jobs
```

Планировщик должен работать как отдельный сервис. Не запускайте его внутри каждого веб-воркера.

## Рекомендуемые пути

```text
/var/www/beacon                     # application directory
/var/www/beacon/venv                # Python virtual environment
/etc/beacon/beacon.conf      # configuration file
/var/lib/beacon                     # SQLite database or runtime state
/var/log/beacon                     # logs
/usr/local/lib/beacon/voice_providers # custom voice providers
```

Beacon читает путь к конфигурации из:

```text
BEACON_CONFIG_FILE
```

Старую переменную `ONCALL_CONFIG_FILE` использовать не следует.

## 1. Установка системных пакетов

Пример для Debian / Ubuntu:

```bash
sudo apt-get update
sudo apt-get install -y \
  git \
  python3 \
  python3-venv \
  python3-pip \
  build-essential \
  curl
```

Если вы используете PostgreSQL, установите также сборочные/runtime-зависимости PostgreSQL:

```bash
sudo apt-get install -y libpq-dev
```

## 2. Клонирование Beacon

```bash
sudo mkdir -p /var/www
sudo git clone https://github.com/glm-labs/Beacon.git /var/www/beacon
cd /var/www/beacon
```

## 3. Создание виртуального окружения

```bash
sudo python3 -m venv /var/www/beacon/venv
sudo /var/www/beacon/venv/bin/pip install --upgrade pip
sudo /var/www/beacon/venv/bin/pip install -r /var/www/beacon/requirements.txt
sudo /var/www/beacon/venv/bin/pip install gunicorn
```

Для инсталляций с PostgreSQL:

```bash
sudo /var/www/beacon/venv/bin/pip install psycopg2-binary
```

## 4. Создание каталогов

```bash
sudo mkdir -p /etc/beacon
sudo mkdir -p /var/lib/beacon
sudo mkdir -p /var/log/beacon
sudo mkdir -p /usr/local/lib/beacon/voice_providers
```

Установите владельца:

```bash
sudo chown -R www-data:www-data /var/www/beacon
sudo chown -R www-data:www-data /var/lib/beacon
sudo chown -R www-data:www-data /var/log/beacon
```

Файлы пользовательских голосовых провайдеров — это исполняемый код Python. Держите этот каталог доступным для записи только администраторам:

```bash
sudo chown root:root /usr/local/lib/beacon/voice_providers
sudo chmod 755 /usr/local/lib/beacon/voice_providers
```

## 5. Создание конфигурации

Создайте:

```text
/etc/beacon/beacon.conf
```

Пример для SQLite:

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

Для продакшена за Nginx или HAProxy задайте `public_base_url` равным реальному внешнему URL:

```ini
[server]
public_base_url = https://beacon.example.com
```

`public_base_url` используется для генерируемых ссылок и URL колбэков.

## 6. Установка сервисов systemd

Скопируйте файлы сервисов:

```bash
sudo cp /var/www/beacon/systemd/beacon.service /etc/systemd/system/
sudo cp /var/www/beacon/systemd/beacon-scheduler.service /etc/systemd/system/
```

Перезагрузите systemd:

```bash
sudo systemctl daemon-reload
```

## 7. Запуск миграций

```bash
cd /var/www/beacon
sudo -u www-data \
  BEACON_CONFIG_FILE=/etc/beacon/beacon.conf \
  /var/www/beacon/venv/bin/python app/migrate.py migrate
```

## 8. Создание первого пользователя-администратора

```bash
cd /var/www/beacon
sudo -u www-data \
  BEACON_CONFIG_FILE=/etc/beacon/beacon.conf \
  /var/www/beacon/venv/bin/python manage.py create-admin \
    --username admin \
    --password 'change-me-123' \
    --email admin@example.com
```

## 9. Запуск сервисов

```bash
sudo systemctl enable beacon
sudo systemctl enable beacon-scheduler

sudo systemctl start beacon
sudo systemctl start beacon-scheduler
```

Проверьте статус:

```bash
sudo systemctl status beacon
sudo systemctl status beacon-scheduler
```

Откройте:

```text
http://SERVER_IP:8080/login
```

## 10. Логи

Логи веб-сервиса:

```bash
journalctl -u beacon -f
```

Логи планировщика:

```bash
journalctl -u beacon-scheduler -f
```

Файл лога приложения:

```bash
tail -f /var/log/beacon/beacon.log
```

## Файлы сервисов systemd

### Веб-сервис

```ini
[Unit]
Description=Beacon Web service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple

User=www-data
Group=www-data

WorkingDirectory=/var/www/beacon

Environment=BEACON_CONFIG_FILE=/etc/beacon/beacon.conf
Environment=BEACON_SERVICE=web
Environment=PYTHONUNBUFFERED=1

ExecStart=/var/www/beacon/venv/bin/gunicorn \
  --bind 0.0.0.0:8080 \
  --workers 1 \
  --threads 4 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile - \
  "app:create_app()"

Restart=always
RestartSec=5

KillSignal=SIGTERM
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
```

### Сервис планировщика

```ini
[Unit]
Description=Beacon Scheduler service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple

User=www-data
Group=www-data

WorkingDirectory=/var/www/beacon

Environment=BEACON_CONFIG_FILE=/etc/beacon/beacon.conf
Environment=BEACON_SERVICE=scheduler
Environment=PYTHONUNBUFFERED=1

ExecStart=/var/www/beacon/venv/bin/python -m app.scheduler_worker

Restart=always
RestartSec=5

KillSignal=SIGTERM
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
```

## Важное замечание о планировщике

Веб-процесс не должен запускать планировщик автоматически.

Правильная модель:

```text
web service:
  create_app()
  no scheduler autostart

scheduler service:
  create_app()
  start_scheduler()
```

Если запуск планировщика сейчас происходит внутри `create_app()`, защитите его условием:

```python
import os

if os.getenv("BEACON_SERVICE") == "scheduler":
    start_scheduler()
```

Если `app.scheduler_worker` запускает планировщик явно, обычно лучше полностью убрать автоматический запуск планировщика из `create_app()`.

## Продакшен с обратным прокси

Для продакшена обычно лучше привязать Gunicorn к localhost и публиковать Beacon через Nginx или HAProxy с HTTPS.

Измените `ExecStart` веб-сервиса:

```ini
ExecStart=/var/www/beacon/venv/bin/gunicorn \
  --bind 127.0.0.1:8080 \
  --workers 1 \
  --threads 4 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile - \
  "app:create_app()"
```

Затем задайте:

```ini
[server]
public_base_url = https://beacon.example.com
```

## Вариант с PostgreSQL

Для более крупных инсталляций используйте PostgreSQL.

Пример секции конфигурации:

```ini
[database]
type = postgresql
host = 127.0.0.1
port = 5432
name = beacon
user = beacon
password = change-me
```

Для PostgreSQL при необходимости увеличьте число веб-воркеров:

```ini
ExecStart=/var/www/beacon/venv/bin/gunicorn \
  --bind 127.0.0.1:8080 \
  --workers 4 \
  --threads 4 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile - \
  "app:create_app()"
```

Для SQLite оставляйте `--workers 1`.

## Обновление Beacon

```bash
cd /var/www/beacon
sudo systemctl stop beacon-scheduler
sudo systemctl stop beacon

sudo git pull
sudo /var/www/beacon/venv/bin/pip install -r requirements.txt

sudo -u www-data \
  BEACON_CONFIG_FILE=/etc/beacon/beacon.conf \
  /var/www/beacon/venv/bin/python app/migrate.py migrate

sudo systemctl start beacon
sudo systemctl start beacon-scheduler
```

## Устранение неполадок

### Файл конфигурации не найден

Проверьте:

```bash
systemctl show beacon --property=Environment
systemctl show beacon-scheduler --property=Environment
```

Проверьте, что файл существует:

```bash
ls -l /etc/beacon/beacon.conf
```

### Отказ в доступе к базе данных SQLite

Проверьте права доступа:

```bash
sudo -u www-data test -w /var/lib/beacon
sudo -u www-data test -r /etc/beacon/beacon.conf
```

### Напоминания дублируются

Проверьте, что планировщик не запущен внутри веб-воркеров и что активен только один сервис планировщика:

```bash
systemctl status beacon-scheduler
ps aux | grep scheduler
```

### Сервис не запускается после обновления кода

Проверьте логи:

```bash
journalctl -u beacon -n 100 --no-pager
journalctl -u beacon-scheduler -n 100 --no-pager
```
