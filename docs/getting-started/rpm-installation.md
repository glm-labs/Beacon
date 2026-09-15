---
title: RPM Installation
description: Install and verify Beacon on RedHat-like distributions from the RPM repository
---

# RPM Installation

Use this guide for RHEL, Rocky Linux, AlmaLinux and CentOS Stream installations.

!!! warning
    A successful `dnf install` transaction only confirms that the RPM files were
    unpacked. Do not expose the service until the Python runtime, configuration,
    migrations and readiness checks below all succeed.

Repository file:

```text
https://repo.beacon.io/beacon.repo
```

## 1. Install the repository file

For DNF-based systems:

```bash
sudo dnf install -y curl openssl
sudo curl -fsSL \
  https://repo.beacon.io/beacon.repo \
  -o /etc/yum.repos.d/beacon.repo
sudo dnf makecache
```

For older yum-based systems:

```bash
sudo yum install -y curl openssl
sudo curl -fsSL \
  https://repo.beacon.io/beacon.repo \
  -o /etc/yum.repos.d/beacon.repo
sudo yum makecache
```

## 2. Install Beacon

```bash
sudo dnf install -y beacon
```

Or with `yum`:

```bash
sudo yum install -y beacon
```

The RPM package installs the application and service files using these paths:

```text
/var/www/beacon                    # application directory
/etc/beacon/beacon.conf     # main configuration file
/var/lib/beacon                    # runtime data, SQLite database by default
/var/log/beacon                    # application logs
/usr/local/lib/beacon/voice_providers # custom voice providers
```

The package should run under the dedicated system user:

```text
beacon
```

## 3. Verify the packaged Python runtime

Beacon requires Python 3.10 or newer. EL9 provides Python 3.9 as
`/usr/bin/python3`, so the web service and scheduler must use the packaged venv,
not the system interpreter.

```bash
rpm -q beacon
sudo test -x /var/www/beacon/venv/bin/python
/var/www/beacon/venv/bin/python --version
/var/www/beacon/venv/bin/python -c \
  'import flask, peewee, gunicorn, joserfc; print("Python dependencies: OK")'
```

The version command must report Python 3.10 or newer and the import command must
finish without an exception.

### Repair an incomplete RPM 2.0-1 runtime on EL9

Some `beacon-2.0-1` builds install the application files but leave the
services on Python 3.9 or omit runtime dependencies. Preserve the packaged venv,
create a Python 3.11 venv and install the application requirements:

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

If a pinned dependency in the RPM requirements file is unavailable, update to a
fixed RPM build. Versions validated as a temporary recovery with 2.0-1 are
`regex==2026.1.15`, `pyTelegramBotAPI==4.32.0` and `Authlib==1.6.12`.

After repairing the venv, repeat the import check above.

## 4. Configure Beacon

Edit:

```bash
sudo vi /etc/beacon/beacon.conf
```

Generate two different secrets with `openssl rand -hex 32`, then review at least:

```ini
[main]
secret_key = replace-with-the-first-random-value
timezone = UTC

[server]
public_base_url = https://beacon.example.com

[database]
type = sqlite
name = /var/lib/beacon/beacon.db

[auth]
jwt_secret = replace-with-the-second-random-value
jwt_cookie_secure = true
```

`secret_key` belongs to `[main]`, not `[server]`. SQLite uses `name`, not
`path`, for the database file. Keep `secret_key` and `jwt_secret` non-empty,
different and stable across restarts. Use the real DNS name or public IP in
`public_base_url`; set `jwt_cookie_secure = true` for HTTPS.

For PostgreSQL, use:

```ini
[database]
type = postgresql
host = 127.0.0.1
port = 5432
name = beacon
user = beacon
password = change-me
```

The 2.0-1 example config may contain duplicate
`alert_group_window_seconds` or `callback_secret` entries. Keep each option only
once and validate the complete file:

```bash
sudo -u beacon \
  /var/www/beacon/venv/bin/python -c \
  'from configparser import ConfigParser; p="/etc/beacon/beacon.conf"; c=ConfigParser(interpolation=None, strict=True); c.read(p); print("Configuration: OK")'
```

Set restrictive permissions and ensure the runtime directories are writable by
the service account:

```bash
sudo chown root:beacon /etc/beacon/beacon.conf
sudo chmod 0640 /etc/beacon/beacon.conf
sudo chown -R beacon:beacon \
  /var/lib/beacon /var/log/beacon
sudo chmod 0750 /var/lib/beacon /var/log/beacon
```

## 5. Make both systemd services use the venv

Inspect the effective units:

```bash
sudo systemctl cat beacon
sudo systemctl cat beacon-scheduler
```

If either unit uses `/usr/bin/python3` or a global `gunicorn`, add systemd
drop-ins. For SQLite, keep one web worker:

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

Apply the changes:

```bash
sudo systemctl daemon-reload
```

## 6. Run database migrations and check the schema

The RPM package may run migrations during installation. If the database was not ready during install, run migrations manually after editing the config:

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

Both commands must exit with status 0.

## 7. Create the first admin user

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

Change the password and email before production use.

## 8. Start and verify services

Enable and start the web service and scheduler:

```bash
sudo systemctl enable --now beacon
sudo systemctl enable --now beacon-scheduler
```

Check service status:

```bash
sudo systemctl status beacon
sudo systemctl status beacon-scheduler
curl -fsS http://127.0.0.1:8080/readyz
```

Follow logs:

```bash
sudo journalctl -u beacon -f
sudo journalctl -u beacon-scheduler -f
```

The packaged service listens on `127.0.0.1:8080`. Do not open port 8080 to the
Internet. Put Nginx or another reverse proxy on ports 80 and 443, configure TLS,
and expose only those ports. On SELinux-enabled systems, allow Nginx to connect
to the local upstream:

```bash
sudo setsebool -P httpd_can_network_connect 1
```

After configuring the proxy, verify from another machine and open:

```text
https://YOUR_PUBLIC_NAME_OR_IP/readyz
https://YOUR_PUBLIC_NAME_OR_IP/login
```

A public IP can use a Let's Encrypt IP certificate with Certbot 5.4 or newer and
the `shortlived` profile. IP certificates are valid for about six days and need
reliable automatic renewal. See the
[Let's Encrypt instructions](https://letsencrypt.org/2026/03/11/shorter-certs-certbot/).

## 9. Optional Telegram worker

Start this service only if Telegram polling or callback processing is used:

```bash
sudo systemctl enable --now beacon-telegram-worker
```

Check logs:

```bash
sudo journalctl -u beacon-telegram-worker -f
```

## 10. Upgrade Beacon

!!! warning "Upgrading from 1.2 to 2.1 or later"
    Beacon 2.1 blocks private/loopback/link-local/reserved outbound HTTP
    destinations unless they are explicitly allowed. Existing internal OIDC
    metadata/JWKS endpoints and outgoing webhooks/API integrations can therefore
    stop working immediately after the upgrade.

Before upgrading, identify internal endpoints used by Beacon and add the
smallest required CIDRs/IPs to the existing configuration:

```ini
[security]
outbound_private_network_allowlist = 10.20.0.0/16,192.168.50.10/32
```

The RPM installs `beacon.conf` as a `noreplace` configuration file, so
an existing configuration is preserved during upgrade. Check for
`/etc/beacon/beacon.conf.rpmnew`, but do not assume the new
security option was merged into your active file automatically. See
[Outbound HTTP network policy](configuration.md#outbound-http-network-policy)
for the DNS behavior and additional examples.

```bash
sudo dnf update -y beacon
```

Or with `yum`:

```bash
sudo yum update -y beacon
```

After upgrade, run migrations if needed:

```bash
cd /var/www/beacon
sudo -u beacon env \
  PYTHONPATH=/var/www/beacon \
  BEACON_CONFIG_FILE=/etc/beacon/beacon.conf \
  /var/www/beacon/venv/bin/python manage.py migrate
```

Then restart services:

```bash
sudo systemctl restart beacon
sudo systemctl restart beacon-scheduler
```

If Telegram worker is used:

```bash
sudo systemctl restart beacon-telegram-worker
```

## 11. Remove Beacon

```bash
sudo dnf remove -y beacon
```

Or with `yum`:

```bash
sudo yum remove -y beacon
```

Configuration and runtime data may remain on disk depending on package removal policy. Remove them manually only when you are sure the data is no longer needed:

```bash
sudo rm -rf /etc/beacon
sudo rm -rf /var/lib/beacon
sudo rm -rf /var/log/beacon
```
