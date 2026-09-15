---
title: Systemd Installation
description: Quick start installation with systemd services
---

# Systemd Installation

This guide describes a classic Linux installation with systemd.

It starts two services:

```text
beacon.service        # HTTP API, UI, webhooks
beacon-scheduler.service  # reminders, escalations, periodic jobs
```

The scheduler must run as a separate service. Do not start it inside every web worker.

## Recommended paths

```text
/var/www/beacon                     # application directory
/var/www/beacon/venv                # Python virtual environment
/etc/beacon/beacon.conf      # configuration file
/var/lib/beacon                     # SQLite database or runtime state
/var/log/beacon                     # logs
/usr/local/lib/beacon/voice_providers # custom voice providers
```

Beacon reads the configuration path from:

```text
BEACON_CONFIG_FILE
```

The old `ONCALL_CONFIG_FILE` variable should not be used.

## 1. Install system packages

Debian / Ubuntu example:

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

If you use PostgreSQL, also install PostgreSQL build/runtime dependencies:

```bash
sudo apt-get install -y libpq-dev
```

## 2. Clone Beacon

```bash
sudo mkdir -p /var/www
sudo git clone https://github.com/glm-labs/Beacon.git /var/www/beacon
cd /var/www/beacon
```

## 3. Create a virtual environment

```bash
sudo python3 -m venv /var/www/beacon/venv
sudo /var/www/beacon/venv/bin/pip install --upgrade pip
sudo /var/www/beacon/venv/bin/pip install -r /var/www/beacon/requirements.txt
sudo /var/www/beacon/venv/bin/pip install gunicorn
```

For PostgreSQL installations:

```bash
sudo /var/www/beacon/venv/bin/pip install psycopg2-binary
```

## 4. Create directories

```bash
sudo mkdir -p /etc/beacon
sudo mkdir -p /var/lib/beacon
sudo mkdir -p /var/log/beacon
sudo mkdir -p /usr/local/lib/beacon/voice_providers
```

Set ownership:

```bash
sudo chown -R www-data:www-data /var/www/beacon
sudo chown -R www-data:www-data /var/lib/beacon
sudo chown -R www-data:www-data /var/log/beacon
```

Custom voice provider files are executable Python code. Keep this directory writable only by administrators:

```bash
sudo chown root:root /usr/local/lib/beacon/voice_providers
sudo chmod 755 /usr/local/lib/beacon/voice_providers
```

## 5. Create config

Create:

```text
/etc/beacon/beacon.conf
```

SQLite example:

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
callback_secret =
```

For production behind Nginx or HAProxy, set `public_base_url` to the real external URL:

```ini
[server]
public_base_url = https://beacon.example.com
```

`public_base_url` is used for generated links and callback URLs.

## 6. Install systemd services

Copy service files:

```bash
sudo cp /var/www/beacon/systemd/beacon.service /etc/systemd/system/
sudo cp /var/www/beacon/systemd/beacon-scheduler.service /etc/systemd/system/
```

Reload systemd:

```bash
sudo systemctl daemon-reload
```

## 7. Run migrations

```bash
cd /var/www/beacon
sudo -u www-data \
  BEACON_CONFIG_FILE=/etc/beacon/beacon.conf \
  /var/www/beacon/venv/bin/python app/migrate.py migrate
```

## 8. Create the first admin user

```bash
cd /var/www/beacon
sudo -u www-data \
  BEACON_CONFIG_FILE=/etc/beacon/beacon.conf \
  /var/www/beacon/venv/bin/python manage.py create-admin \
    --username admin \
    --password 'change-me-123' \
    --email admin@example.com
```

## 9. Start services

```bash
sudo systemctl enable beacon
sudo systemctl enable beacon-scheduler

sudo systemctl start beacon
sudo systemctl start beacon-scheduler
```

Check status:

```bash
sudo systemctl status beacon
sudo systemctl status beacon-scheduler
```

Open:

```text
http://SERVER_IP:8080/login
```

## 10. Logs

Web logs:

```bash
journalctl -u beacon -f
```

Scheduler logs:

```bash
journalctl -u beacon-scheduler -f
```

Application log file:

```bash
tail -f /var/log/beacon/beacon.log
```

## Systemd service files

### Web service

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

### Scheduler service

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

## Important scheduler note

The web process must not start the scheduler automatically.

Correct model:

```text
web service:
  create_app()
  no scheduler autostart

scheduler service:
  create_app()
  start_scheduler()
```

If scheduler startup currently happens inside `create_app()`, guard it:

```python
import os

if os.getenv("BEACON_SERVICE") == "scheduler":
    start_scheduler()
```

If `app.scheduler_worker` starts the scheduler explicitly, it is usually better to remove automatic scheduler startup from `create_app()` completely.

## Production with reverse proxy

For production, it is usually better to bind Gunicorn to localhost and expose Beacon through Nginx or HAProxy with HTTPS.

Change web service `ExecStart`:

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

Then set:

```ini
[server]
public_base_url = https://beacon.example.com
```

## PostgreSQL variant

For larger installations, use PostgreSQL.

Example config section:

```ini
[database]
type = postgresql
host = 127.0.0.1
port = 5432
name = beacon
user = beacon
password = change-me
```

For PostgreSQL, increase web workers if needed:

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

For SQLite, keep `--workers 1`.

## Update Beacon

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

## Troubleshooting

### Config file not found

Check:

```bash
systemctl show beacon --property=Environment
systemctl show beacon-scheduler --property=Environment
```

Check file exists:

```bash
ls -l /etc/beacon/beacon.conf
```

### Permission denied for SQLite database

Check permissions:

```bash
sudo -u www-data test -w /var/lib/beacon
sudo -u www-data test -r /etc/beacon/beacon.conf
```

### Reminders are duplicated

Check that the scheduler is not running inside web workers and that only one scheduler service is active:

```bash
systemctl status beacon-scheduler
ps aux | grep scheduler
```

### Service does not start after code update

Check logs:

```bash
journalctl -u beacon -n 100 --no-pager
journalctl -u beacon-scheduler -n 100 --no-pager
```
