---
title: Docker Installation
description: Run Beacon with Docker Compose
---

# Docker Installation

Docker Compose is the fastest way to run Beacon for testing, demos and simple self-hosted deployments.

The default Compose setup starts:

```text
beacon             # HTTP API, UI, incoming webhooks
beacon-scheduler   # reminders, escalations, periodic jobs
beacon-telegram    # Telegram callbacks / polling worker
beacon-slack       # Slack Socket Mode worker
```

The Telegram and Slack workers are harmless when the corresponding integrations are not configured. PostgreSQL is optional. SQLite is suitable for small installations and quick starts.

## Default architecture

```text
Docker Compose
├── beacon
│   └── Gunicorn + Flask application
├── beacon-scheduler
│   └── standalone scheduler worker
├── beacon-telegram
│   └── Telegram callbacks / polling
├── beacon-slack
│   └── Slack Socket Mode interactions
└── beacon-data
    └── SQLite database volume
```

Default SQLite path inside the container:

```text
/var/lib/beacon/beacon.db
```

Default config path inside the container:

```text
/etc/beacon/beacon.conf
```

The config file is selected by:

```text
BEACON_CONFIG_FILE
```

## Quick start with SQLite

```bash
docker compose up -d
```

Open the UI:

```text
http://SERVER_IP:8080/login
```

Show logs:

```bash
docker compose logs -f beacon
docker compose logs -f beacon-scheduler
```

## Run migrations

If migrations are not run automatically by your container entrypoint, run:

```bash
docker compose exec beacon python manage.py migrate
```

## Create the first admin user

```bash
docker compose exec beacon \
  python manage.py create-admin \
    --username admin \
    --password 'change-me-123' \
    --email admin@example.com
```

Change the password and email before production use.

## Default SQLite config

File:

```text
docker/beacon.docker.conf
```

Example:

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
name = /var/lib/beacon/beacon.db

[sqlite]
wal = true
busy_timeout = 5000

[voice]
provider = stub
providers_dir = /usr/local/lib/beacon/voice_providers
callback_secret =
```

## PostgreSQL variant

Use PostgreSQL for:

- larger teams;
- higher alert volume;
- multiple web workers;
- longer-term production installations.

Start with PostgreSQL if the repository provides a PostgreSQL Compose override:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.postgres.yml \
  up -d
```

PostgreSQL config example:

```ini
[database]
type = postgresql
host = postgres
port = 5432
name = beacon
user = beacon
password = beacon-change-me
```

## External access

With this mapping:

```yaml
ports:
  - "8080:8080"
```

Beacon is available on:

```text
http://SERVER_IP:8080
```

if the firewall allows port `8080`.

For production, it is better to expose Beacon through Nginx or HAProxy with HTTPS:

```text
Internet -> Nginx/HAProxy :443 -> Beacon :8080
```

Set the public URL correctly:

```ini
[server]
public_base_url = https://beacon.example.com
```

`public_base_url` is used for generated links and callbacks.

## Custom voice providers

Custom voice providers can be mounted into:

```text
/usr/local/lib/beacon/voice_providers
```

Example Compose mount:

```yaml
volumes:
  - ./custom_voice_providers:/usr/local/lib/beacon/voice_providers:ro
```

After changing provider files, restart the containers:

```bash
docker compose restart beacon beacon-scheduler
```
