---
title: Kubernetes Installation
description: Deploy Beacon to Kubernetes with the bundled Helm chart
---

# Kubernetes Installation

The Beacon Helm chart is published as an OCI artifact in GHCR and is also kept in this repository at `helm/beacon`. It deploys the web application and the background workers, renders the application config into a Secret, and wires the `/healthz` and `/readyz` probes to Kubernetes.

## Requirements

```text
Kubernetes 1.23+
Helm 3.8+ or Helm 4
a StorageClass, if you keep the default SQLite setup
```

## What the chart deploys

```text
Deployment  <release>-web        Gunicorn + Flask application
Deployment  <release>-scheduler  reminders, escalations, periodic jobs
Deployment  <release>-telegram   Telegram callback worker (optional)
Deployment  <release>-slack      Slack Socket Mode worker (optional)
Service     <release>            ClusterIP on port 8080
Secret      <release>-config     rendered beacon.conf
PersistentVolumeClaim <release>-data   /var/lib/beacon
ServiceAccount, and an Ingress when enabled
```

Each component runs the same image and is selected by `BEACON_SERVICE`, exactly as in the Docker Compose setup.

## Quick start

```bash
helm install beacon \
  oci://ghcr.io/glm-labs/beacon-charts/beacon \
  --version 2.1.0 \
  --set-string config.main.secret_key="$(openssl rand -hex 32)"
```

OCI support is enabled by default in Helm 3.8 and later. No `helm repo add` step is required. The chart pulls `ghcr.io/glm-labs/beacon` and defaults the image tag to the chart `appVersion`. To pin an explicit image:

```bash
helm upgrade --install beacon \
  oci://ghcr.io/glm-labs/beacon-charts/beacon \
  --version 2.1.0 \
  --set image.repository=ghcr.io/glm-labs/beacon \
  --set image.tag=2.1 \
  --set-string config.main.secret_key="$(openssl rand -hex 32)"
```

### Install from a source checkout

For chart development or testing unreleased changes, install the bundled chart directly:

```bash
helm upgrade --install beacon ./helm/beacon \
  --set-string config.main.secret_key="$(openssl rand -hex 32)"
```

Watch the rollout:

```bash
kubectl get pods -l app.kubernetes.io/instance=beacon -w
```

## Configuration

Beacon reads every setting from a single INI file mounted at `/etc/beacon/beacon.conf`. The chart renders that file from the `config` map in `values.yaml`: top-level keys become INI sections, nested keys become options.

```yaml
config:
  main:
    secret_key: ""
  auth:
    api_auth_required: true
    rbac_enforced: true
    jwt_secret: ""
  server:
    host: 0.0.0.0
    port: 8080
    public_base_url: https://beacon.example.com
```

becomes:

```ini
[main]
secret_key =

[auth]
api_auth_required = true
rbac_enforced = true
jwt_secret = <same shared secret when left empty in values.yaml>

[server]
host = 0.0.0.0
port = 8080
public_base_url = https://beacon.example.com
```

Anything valid in `beacon.conf` can be set this way. See [Configuration](configuration.md) for the available options.

Set `public_base_url` to the address users actually reach. It is used for generated links and callbacks.

For chart-rendered configuration, `config.main.secret_key` is required. Beacon 2.0 uses it as the shared fallback for `main.secret_encryption_key`, `auth.jwt_secret`, `mattermost.action_secret`, and `voice.callback_secret` when those values are empty. This is intentional: every pod must use stable shared signing/encryption keys, especially when PostgreSQL is used and `/var/lib/beacon` is not shared. You can override any of those values with a separate random secret.

### Bring your own Secret

The rendered file carries credentials, so the chart stores it in a Secret. To manage that Secret yourself instead, create one with the whole config under the key `beacon.conf` and point the chart at it:

```bash
kubectl create secret generic beacon-config \
  --from-file=beacon.conf=./beacon.conf
```

```yaml
existingConfigSecret: beacon-config
```

When `existingConfigSecret` is set, the `config` map is ignored and the chart renders no Secret of its own.

!!! note
    The chart adds a `checksum/config` pod annotation so config changes restart the pods automatically. With `existingConfigSecret` the chart cannot see the content, so the annotation is omitted — restart the pods yourself after changing the Secret.

## Database

### SQLite (default)

SQLite works out of the box. All components mount one PersistentVolumeClaim for `/var/lib/beacon`.

```yaml
persistence:
  enabled: true
  accessModes:
    - ReadWriteOnce
  size: 1Gi
  storageClass: ""
```

!!! warning
    SQLite is supported only with `persistence.enabled=true` and `web.replicaCount=1`. For chart-rendered SQLite configuration, the chart automatically adds required pod affinity to scheduler/Telegram/Slack workers so they run on the web pod's node and can mount the same ReadWriteOnce claim. SQLite over network-backed ReadWriteMany storage such as NFS is still unsafe. For anything multi-node or horizontally scaled, use PostgreSQL.

The PVC is created by the chart and therefore removed by `helm uninstall`. To keep the data, create the claim yourself and reference it:

```yaml
persistence:
  existingClaim: beacon-data
```

### PostgreSQL

For production, point the chart at PostgreSQL and turn persistence off:

```yaml
config:
  database:
    type: postgresql
    host: postgres.example.svc
    port: 5432
    name: beacon
    user: beacon
    password: <database-password>

persistence:
  enabled: false
```

## Migrations and scaling the web component

By default the web pod runs migrations in its entrypoint before Gunicorn starts:

```yaml
web:
  runMigrations: true
  replicaCount: 1
```

Keep `replicaCount` at `1` while this is on — several pods starting at once would race on the migrations. To run more than one web replica, disable it and migrate out of band:

```bash
kubectl exec deploy/beacon-web -- python manage.py migrate
```

```yaml
web:
  runMigrations: false
  replicaCount: 3
  strategy:
    type: RollingUpdate
```

`RollingUpdate` is only appropriate with PostgreSQL. On the shared SQLite volume keep the default `Recreate`, which prevents the old and new pod from writing one database file during a rollout.

## Health probes

The web deployment is wired to the unauthenticated probe endpoints:

```text
/healthz  liveness   200 as long as the process serves requests; does not touch the database
/readyz   readiness  200 only when the database is reachable and all migrations are applied
```

A startup probe allows up to five minutes for the first boot, which covers migrations on a fresh database.

## Access

By default the Service is `ClusterIP`. For a quick look:

```bash
kubectl port-forward svc/beacon 8080:8080
```

```text
http://127.0.0.1:8080/login
```

For permanent access, enable the Ingress:

```yaml
ingress:
  enabled: true
  className: nginx
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt
  hosts:
    - host: beacon.example.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - hosts:
        - beacon.example.com
      secretName: beacon-tls
```

Keep `config.server.public_base_url` in sync with the Ingress host.

## Create the first admin user

```bash
kubectl exec -it deploy/beacon-web -- \
  python manage.py create-admin \
    --username admin \
    --password 'change-me-123' \
    --email admin@example.com
```

Change the password before production use, then continue with [First Login and Setup](first-login.md).

## Workers

The scheduler evaluates rotations, reminders and escalations. It is required for reminders and escalations to work at all:

```yaml
scheduler:
  enabled: true
```

The Telegram worker processes callback buttons. It idles harmlessly without a configured bot:

```yaml
telegram:
  enabled: true
```

The Slack worker holds the Socket Mode WebSocket that carries interactive `Acknowledge` and `Resolve` buttons. Slack messages themselves are sent by the web component, so without this worker notifications still arrive — only their buttons do nothing:

```yaml
slack:
  enabled: true
```

It idles without a configured Slack channel, and picks up channel configuration from the database on its own, so no pod restart is needed after adding one. Socket Mode needs no public Request URL, which makes it the usual choice for clusters that are not exposed to the internet. See [Slack](../integrations/slack.md) for the Slack app setup.

Each component accepts the usual placement and sizing knobs:

```yaml
scheduler:
  resources:
    requests:
      cpu: 100m
      memory: 256Mi
  nodeSelector: {}
  tolerations: []
  affinity: {}
  extraEnv: []
```

## Logs

The application writes JSON logs to files under `/var/log/beacon`, not to standard output, so `kubectl logs` shows only the entrypoint banner. Read the files directly:

```bash
kubectl exec deploy/beacon-web -- tail -f /var/log/beacon/beacon.log
kubectl exec deploy/beacon-scheduler -- tail -f /var/log/beacon/beacon-scheduler.log
```

The log volume is an `emptyDir`, so these files do not survive a pod restart. See [Logging](../administration/logging.md) for the file layout.

## Custom voice providers

Mount provider plugins into every component with the shared extra volumes:

```yaml
extraVolumes:
  - name: voice-providers
    configMap:
      name: beacon-voice-providers

extraVolumeMounts:
  - name: voice-providers
    mountPath: /usr/local/lib/beacon/voice_providers
    readOnly: true
```

## Upgrade and uninstall

### Upgrading from 1.2 to 2.1 or later

!!! warning
    Beacon 2.1 blocks private/loopback/link-local/reserved outbound HTTP
    destinations unless they are explicitly allowed. Internal OIDC
    metadata/JWKS endpoints and outgoing webhook/API integrations that worked in
    1.2 can therefore stop working after the chart upgrade.

For chart-rendered configuration, add the required internal CIDRs/IPs before
the upgrade:

```yaml
config:
  security:
    outbound_private_network_allowlist: "10.20.0.0/16,192.168.50.10/32"
```

If you use `existingConfigSecret`, update its `beacon.conf` instead:

```ini
[security]
outbound_private_network_allowlist = 10.20.0.0/16,192.168.50.10/32
```

Resolve internal hostnames from the cluster and allow only the addresses that
Beacon actually needs. See
[Outbound HTTP network policy](configuration.md#outbound-http-network-policy)
for DNS fail-closed behavior and additional examples.

### Upgrading from 1.x to 2.0

The 2.0 chart can reuse 1.x values. During rendering it materializes the new secure auth defaults and shared JWT/encryption/callback secrets before creating `beacon.conf`, so old values do not cause different pods to generate different runtime keys. `config.main.secret_key` must still be present and must be a unique random value.

If you use `existingConfigSecret`, Helm cannot normalize that external file. Before the 2.0 upgrade, make sure it contains a valid `main.secret_key`, enables the desired `[auth]` settings, and uses a stable `auth.jwt_secret` (or omits/leaves it empty so the application falls back to `main.secret_key`).

For SQLite, keep `persistence.enabled=true` and `web.replicaCount=1`. For PostgreSQL/multi-node deployments, set `persistence.enabled=false` once every security secret is stable in the rendered or external config.

```bash
helm upgrade beacon \
  oci://ghcr.io/glm-labs/beacon-charts/beacon \
  --version 2.1.0 \
  --reuse-values
```

```bash
helm uninstall beacon
```

`helm uninstall` also deletes the PersistentVolumeClaim created by the chart, and with it the SQLite database. Use `persistence.existingClaim` if you need the data to outlive the release.
