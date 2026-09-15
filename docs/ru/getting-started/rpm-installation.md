---
title: Установка через RPM
description: Установка и проверка Beacon на RedHat-подобных дистрибутивах из RPM-репозитория
---

# Установка через RPM

Используйте это руководство для инсталляций на RHEL, Rocky Linux, AlmaLinux и CentOS Stream.

!!! warning
    Успешная команда `dnf install` означает только то, что файлы RPM распакованы.
    Не публикуйте сервис, пока не пройдут проверки Python, конфигурации,
    миграций и readiness из этого руководства.

Файл репозитория:

```text
https://repo.beacon.io/beacon.repo
```

## 1. Установка файла репозитория

Для систем на основе DNF:

```bash
sudo dnf install -y curl openssl
sudo curl -fsSL \
  https://repo.beacon.io/beacon.repo \
  -o /etc/yum.repos.d/beacon.repo
sudo dnf makecache
```

Для более старых систем на основе yum:

```bash
sudo yum install -y curl openssl
sudo curl -fsSL \
  https://repo.beacon.io/beacon.repo \
  -o /etc/yum.repos.d/beacon.repo
sudo yum makecache
```

## 2. Установка Beacon

```bash
sudo dnf install -y beacon
```

Или с помощью `yum`:

```bash
sudo yum install -y beacon
```

RPM-пакет устанавливает приложение и файлы сервисов, используя следующие пути:

```text
/var/www/beacon                    # application directory
/etc/beacon/beacon.conf     # main configuration file
/var/lib/beacon                    # runtime data, SQLite database by default
/var/log/beacon                    # application logs
/usr/local/lib/beacon/voice_providers # custom voice providers
```

Пакет должен работать под выделенным системным пользователем:

```text
beacon
```

## 3. Проверка Python-runtime из пакета

Beacon требует Python 3.10 или новее. В EL9 команда `/usr/bin/python3`
запускает Python 3.9, поэтому веб-сервис и планировщик должны использовать venv
из пакета, а не системный интерпретатор.

```bash
rpm -q beacon
sudo test -x /var/www/beacon/venv/bin/python
/var/www/beacon/venv/bin/python --version
/var/www/beacon/venv/bin/python -c \
  'import flask, peewee, gunicorn, joserfc; print("Python dependencies: OK")'
```

Команда версии должна показать Python 3.10 или новее, а проверка импортов должна
завершиться без исключения.

### Восстановление неполного runtime RPM 2.0-1 в EL9

Некоторые сборки `beacon-2.0-1` устанавливают код, но оставляют сервисы
на Python 3.9 или не устанавливают часть зависимостей. Сохраните окружение из
пакета, создайте venv Python 3.11 и установите зависимости:

```bash
sudo dnf install -y python3.11 python3.11-pip
if sudo test -e /var/www/beacon/venv; then
  sudo mv /var/www/beacon/venv \
    "/var/www/beacon/venv.rpm-backup.$(date +%Y%m%d%H%M%S)"
fi
sudo /usr/bin/python3.11 -m venv /var/www/beacon/venv
sudo /var/www/beacon/venv/bin/python -m pip install --upgrade pip
sudo /var/www/beacon/venv/bin/python -m pip install \
  -r /var/www/beacon/requirements.txt \
  gunicorn joserfc
sudo chown -R root:beacon /var/www/beacon/venv
sudo chmod -R g+rX,o-rwx /var/www/beacon/venv
```

Если версия зависимости из requirements RPM отсутствует, установите исправленную
сборку пакета. Проверенные как временное восстановление для 2.0-1 версии:
`regex==2026.1.15`, `pyTelegramBotAPI==4.32.0` и `Authlib==1.6.12`.

После восстановления venv повторите проверку импортов.

## 4. Настройка Beacon

Отредактируйте:

```bash
sudo vi /etc/beacon/beacon.conf
```

Сгенерируйте два разных секрета командой `openssl rand -hex 32`, затем проверьте
как минимум:

```ini
[main]
secret_key = замените-на-первое-случайное-значение
timezone = UTC

[server]
public_base_url = https://beacon.example.com

[database]
type = sqlite
name = /var/lib/beacon/beacon.db

[auth]
jwt_secret = замените-на-второе-случайное-значение
jwt_cookie_secure = true
```

`secret_key` относится к `[main]`, а не к `[server]`. Для файла SQLite
используется `name`, а не `path`. Значения `secret_key` и `jwt_secret` должны
быть непустыми, разными и постоянными. Укажите реальное DNS-имя или публичный IP
в `public_base_url`; для HTTPS установите `jwt_cookie_secure = true`.

Для PostgreSQL используйте:

```ini
[database]
type = postgresql
host = 127.0.0.1
port = 5432
name = beacon
user = beacon
password = change-me
```

В примере конфигурации 2.0-1 могут повторяться параметры
`alert_group_window_seconds` и `callback_secret`. Оставьте каждый параметр один
раз и проверьте весь файл:

```bash
sudo -u beacon \
  /var/www/beacon/venv/bin/python -c \
  'from configparser import ConfigParser; p="/etc/beacon/beacon.conf"; c=ConfigParser(interpolation=None, strict=True); c.read(p); print("Configuration: OK")'
```

Закройте права на конфигурацию и разрешите сервису запись в runtime-каталоги:

```bash
sudo chown root:beacon /etc/beacon/beacon.conf
sudo chmod 0640 /etc/beacon/beacon.conf
sudo chown -R beacon:beacon \
  /var/lib/beacon /var/log/beacon
sudo chmod 0750 /var/lib/beacon /var/log/beacon
```

## 5. Перевод обоих systemd-сервисов на venv

Посмотрите итоговые unit-файлы:

```bash
sudo systemctl cat beacon
sudo systemctl cat beacon-scheduler
```

Если unit использует `/usr/bin/python3` или глобальный `gunicorn`, добавьте
systemd drop-in. Для SQLite оставьте один веб-воркер:

```bash
sudo systemctl edit beacon
```

```ini
[Service]
ExecStart=
ExecStart=/var/www/beacon/venv/bin/python -m gunicorn --workers 1 --threads 4 --timeout 120 --bind 127.0.0.1:8080 --access-logfile /var/log/beacon/gun-beacon.log --error-logfile /var/log/beacon/gun-beacon_error.log --capture-output app:create_app()
UMask=0027
```

```bash
sudo systemctl edit beacon-scheduler
```

```ini
[Service]
ExecStart=
ExecStart=/var/www/beacon/venv/bin/python -m app.scheduler_worker
UMask=0027
```

Примените изменения:

```bash
sudo systemctl daemon-reload
```

## 6. Миграции и проверка схемы

RPM-пакет может запускать миграции во время установки. Если база данных не была готова во время установки, запустите миграции вручную после редактирования конфигурации:

```bash
cd /var/www/beacon
sudo -u beacon env \
  PYTHONPATH=/var/www/beacon \
  BEACON_CONFIG_FILE=/etc/beacon/beacon.conf \
  /var/www/beacon/venv/bin/python manage.py migrate

sudo -u beacon env \
  PYTHONPATH=/var/www/beacon \
  BEACON_CONFIG_FILE=/etc/beacon/beacon.conf \
  /var/www/beacon/venv/bin/python -m app.check_schema
```

Обе команды должны завершиться с кодом 0.

## 7. Создание первого пользователя-администратора

```bash
cd /var/www/beacon
sudo -u beacon env \
  PYTHONPATH=/var/www/beacon \
  BEACON_CONFIG_FILE=/etc/beacon/beacon.conf \
  /var/www/beacon/venv/bin/python manage.py create-admin \
    --username admin \
    --password 'change-me-123' \
    --email admin@example.com
```

Смените пароль и email перед использованием в продакшене.

## 8. Запуск и проверка сервисов

Включите и запустите веб-сервис и планировщик:

```bash
sudo systemctl enable --now beacon
sudo systemctl enable --now beacon-scheduler
```

Проверьте статус сервисов:

```bash
sudo systemctl status beacon
sudo systemctl status beacon-scheduler
curl -fsS http://127.0.0.1:8080/readyz
```

Следите за логами:

```bash
sudo journalctl -u beacon -f
sudo journalctl -u beacon-scheduler -f
```

Веб-сервис из пакета слушает `127.0.0.1:8080`. Не открывайте порт 8080 в
Интернет. Используйте Nginx или другой reverse proxy на портах 80 и 443 и
настройте TLS. В системах с SELinux разрешите Nginx подключаться к локальному
upstream:

```bash
sudo setsebool -P httpd_can_network_connect 1
```

После настройки proxy проверьте с другой машины и откройте:

```text
https://YOUR_PUBLIC_NAME_OR_IP/readyz
https://YOUR_PUBLIC_NAME_OR_IP/login
```

Для публичного IP можно использовать IP-сертификат Let's Encrypt с Certbot 5.4
или новее и профилем `shortlived`. Такой сертификат действует около шести дней,
поэтому автоматическое продление обязательно. См.
[инструкцию Let's Encrypt](https://letsencrypt.org/2026/03/11/shorter-certs-certbot/).

## 9. Опциональный Telegram-воркер

Запускайте этот сервис, только если используется polling Telegram или обработка колбэков:

```bash
sudo systemctl enable --now beacon-telegram-worker
```

Проверьте логи:

```bash
sudo journalctl -u beacon-telegram-worker -f
```

## 10. Обновление Beacon

!!! warning "Обновление с 1.2 на 2.1 или новее"
    Beacon 2.1 блокирует private/loopback/link-local/reserved адреса
    исходящих HTTP-запросов, если они не разрешены явно. Поэтому существующие
    внутренние OIDC metadata/JWKS endpoints и исходящие webhook/API-интеграции
    могут перестать работать сразу после обновления.

До обновления определите внутренние endpoints, к которым обращается
Beacon, и добавьте минимально необходимые CIDR/IP в текущую конфигурацию:

```ini
[security]
outbound_private_network_allowlist = 10.20.0.0/16,192.168.50.10/32
```

RPM устанавливает `beacon.conf` как конфигурацию `noreplace`, поэтому
существующий файл сохраняется при обновлении. Проверьте наличие
`/etc/beacon/beacon.conf.rpmnew`, но не рассчитывайте, что новый
security-параметр автоматически попадёт в активный конфиг. Подробности о DNS и
дополнительные примеры см. в разделе
[Политика исходящих HTTP-подключений](configuration.md#политика-исходящих-http-подключений).

```bash
sudo dnf update -y beacon
```

Или с помощью `yum`:

```bash
sudo yum update -y beacon
```

После обновления запустите миграции при необходимости:

```bash
cd /var/www/beacon
sudo -u beacon env \
  PYTHONPATH=/var/www/beacon \
  BEACON_CONFIG_FILE=/etc/beacon/beacon.conf \
  /var/www/beacon/venv/bin/python manage.py migrate
```

Затем перезапустите сервисы:

```bash
sudo systemctl restart beacon
sudo systemctl restart beacon-scheduler
```

Если используется Telegram-воркер:

```bash
sudo systemctl restart beacon-telegram-worker
```

## 11. Удаление Beacon

```bash
sudo dnf remove -y beacon
```

Или с помощью `yum`:

```bash
sudo yum remove -y beacon
```

Конфигурация и runtime-данные могут остаться на диске в зависимости от политики удаления пакета. Удаляйте их вручную только когда вы уверены, что данные больше не нужны:

```bash
sudo rm -rf /etc/beacon
sudo rm -rf /var/lib/beacon
sudo rm -rf /var/log/beacon
```
