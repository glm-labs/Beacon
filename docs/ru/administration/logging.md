---
title: Журналирование
description: Расположение журналов Beacon, поля и заметки по устранению неполадок.
---

# Журналирование

Beacon пишет структурированные логи в стиле JSON для приёма алертов, уведомлений, активности планировщика и ошибок.

## Где искать

Установки systemd:

```bash
journalctl -u beacon -f
journalctl -u beacon-scheduler -f
```

Установки RPM используют те же имена сервисов:

```bash
journalctl -u beacon -f
journalctl -u beacon-scheduler -f
journalctl -u beacon-telegram-worker -f
```

Установки Docker:

```bash
docker compose logs -f beacon
docker compose logs -f beacon-scheduler
```

Если настроено журналирование в файл:

```bash
tail -f /var/log/beacon/beacon.log
```

## Полезные поля

Общие поля:

```text
timestamp
level
logger
message
module
function
line
```

Поля алертов и уведомлений:

```text
alert_id
team
route_id
routing_error
channel_id
channel_name
channel_type
event_type
provider
error
```

## Логи уведомлений

`notification sent` означает, что Beacon передал сообщение нижестоящему провайдеру или SMTP-релею без исключения. Это не гарантирует итоговую доставку.

Если пользователь не получил сообщение, проверьте также логи нижестоящего сервиса.
