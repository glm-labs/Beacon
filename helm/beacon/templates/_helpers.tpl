{{/*
Expand the name of the chart.
*/}}
{{- define "beacon.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name (63 char limit).
*/}}
{{- define "beacon.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Chart name and version for the chart label.
*/}}
{{- define "beacon.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels.
*/}}
{{- define "beacon.labels" -}}
helm.sh/chart: {{ include "beacon.chart" . }}
{{ include "beacon.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels.
*/}}
{{- define "beacon.selectorLabels" -}}
app.kubernetes.io/name: {{ include "beacon.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Service account name.
*/}}
{{- define "beacon.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "beacon.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Image reference.
*/}}
{{- define "beacon.image" -}}
{{- printf "%s:%s" .Values.image.repository (default .Chart.AppVersion .Values.image.tag) }}
{{- end }}

{{/*
Name of the Secret holding beacon.conf.
*/}}
{{- define "beacon.configSecretName" -}}
{{- default (printf "%s-config" (include "beacon.fullname" .)) .Values.existingConfigSecret }}
{{- end }}

{{/*
Validate chart-rendered configuration before creating workloads. Use get/default
so upgrades that reuse pre-2.0 values fail cleanly instead of dereferencing a
missing nested map.
*/}}
{{- define "beacon.validateValues" -}}
{{- if not .Values.existingConfigSecret -}}
{{- $config := default (dict) .Values.config -}}
{{- $main := default (dict) (get $config "main") -}}
{{- $mainSecret := required "config.main.secret_key is required; set a unique random value or use existingConfigSecret" (get $main "secret_key") -}}
{{- $knownInsecure := list "dev-secret-key" "change-me" "change-this-secret-key" "change-this-jwt-secret" "change-this-mattermost-action-secret" -}}
{{- if has ($mainSecret | toString | trim) $knownInsecure -}}
{{- fail "config.main.secret_key uses a known insecure default; set a unique cryptographically random value" -}}
{{- end -}}
{{- $secretEncryptionKey := default $mainSecret (get $main "secret_encryption_key") -}}
{{- if has ($secretEncryptionKey | toString | trim) $knownInsecure -}}
{{- fail "config.main.secret_encryption_key uses a known insecure default; set a unique cryptographically random value or leave it empty to inherit main.secret_key" -}}
{{- end -}}
{{- $auth := default (dict) (get $config "auth") -}}
{{- $jwtSecret := default $mainSecret (get $auth "jwt_secret") -}}
{{- if has ($jwtSecret | toString | trim) $knownInsecure -}}
{{- fail "config.auth.jwt_secret uses a known insecure default; set a unique cryptographically random value or leave it empty to inherit main.secret_key" -}}
{{- end -}}
{{- $mattermost := default (dict) (get $config "mattermost") -}}
{{- $mattermostSecret := default $mainSecret (get $mattermost "action_secret") -}}
{{- if has ($mattermostSecret | toString | trim) $knownInsecure -}}
{{- fail "config.mattermost.action_secret uses a known insecure default; set a unique cryptographically random value or leave it empty to inherit main.secret_key" -}}
{{- end -}}
{{- $voice := default (dict) (get $config "voice") -}}
{{- $voiceSecret := default $mainSecret (get $voice "callback_secret") -}}
{{- if has ($voiceSecret | toString | trim) $knownInsecure -}}
{{- fail "config.voice.callback_secret uses a known insecure default; set a unique cryptographically random value or leave it empty to inherit main.secret_key" -}}
{{- end -}}
{{- $database := default (dict) (get $config "database") -}}
{{- $dbType := default "sqlite" (get $database "type") | toString -}}
{{- if and (eq $dbType "sqlite") (not .Values.persistence.enabled) -}}
{{- fail "SQLite requires persistence.enabled=true so web and worker pods share the same database; use PostgreSQL before disabling persistence" -}}
{{- end -}}
{{- if and (eq $dbType "sqlite") (gt (int .Values.web.replicaCount) 1) -}}
{{- fail "SQLite supports only web.replicaCount=1 in this chart; use PostgreSQL before scaling the web deployment" -}}
{{- end -}}
{{- end -}}
{{- end }}

{{/*
Return a normalized 2.0 config map. This makes old Helm values safe to reuse:
security-related options introduced after 1.x are materialized before the INI
file is rendered, so the container entrypoint never generates different keys
inside separate PostgreSQL/multi-node pods.
*/}}
{{- define "beacon.config" -}}
{{- if not .Values.existingConfigSecret -}}
{{- include "beacon.validateValues" . -}}
{{- end -}}
{{- $config := deepCopy (default (dict) .Values.config) -}}
{{- $main := default (dict) (get $config "main") -}}
{{- $mainSecret := default "" (get $main "secret_key") -}}
{{- $_ := set $main "secret_encryption_key" (default $mainSecret (get $main "secret_encryption_key")) -}}
{{- $_ = set $config "main" $main -}}

{{- $authDefaults := dict
      "api_auth_required" true
      "rbac_enforced" true
      "jwt_secret" ""
      "jwt_expire_minutes" 1440
      "jwt_cookie_name" "beacon_jwt"
      "jwt_cookie_secure" false
      "login_ip_max_failures" 60
      "login_ip_window_seconds" 60
      "login_ip_block_seconds" 60
      "login_account_max_failures" 20
      "login_account_window_seconds" 300
      "login_account_block_seconds" 300 -}}
{{- $auth := mergeOverwrite $authDefaults (default (dict) (get $config "auth")) -}}
{{- $_ = set $auth "jwt_secret" (default $mainSecret (get $auth "jwt_secret")) -}}
{{- $_ = set $config "auth" $auth -}}

{{- $mattermost := default (dict) (get $config "mattermost") -}}
{{- $_ = set $mattermost "action_secret" (default $mainSecret (get $mattermost "action_secret")) -}}
{{- $_ = set $config "mattermost" $mattermost -}}

{{- $voice := default (dict) (get $config "voice") -}}
{{- $_ = set $voice "callback_secret" (default $mainSecret (get $voice "callback_secret")) -}}
{{- $_ = set $config "voice" $voice -}}

{{ range $section, $options := $config -}}
[{{ $section }}]
{{ range $key, $value := $options -}}
{{ $key }} = {{ include "beacon.iniValue" $value }}
{{ end }}
{{ end -}}
{{- end }}

{{/*
Render one INI value.

Helm unmarshals every YAML number into a float64, and Go prints a float64
of a million or more in scientific notation. The default
`outbound_http_max_response_bytes: 1048576` would therefore reach the pod
as `1.048576e+06`, which settings.get_int() cannot parse, so the web pod
crashes on startup. Whole numbers are written as integers here, so any
value can be written plainly in values.yaml.
*/}}
{{- define "beacon.iniValue" -}}
{{- if and (kindIs "float64" .) (eq . (floor .)) -}}
{{- int64 . -}}
{{- else -}}
{{- . -}}
{{- end -}}
{{- end }}


{{/*
Keep worker pods on the web pod's node whenever the shared data volume is
enabled. This makes the default ReadWriteOnce PVC schedulable for every worker
and also keeps the SQLite deployment on one node.
*/}}
{{- define "beacon.dataWorkerAffinity" -}}
podAffinity:
  requiredDuringSchedulingIgnoredDuringExecution:
    - labelSelector:
        matchLabels:
          {{- include "beacon.selectorLabels" . | nindent 10 }}
          app.kubernetes.io/component: web
      topologyKey: kubernetes.io/hostname
{{- end }}

{{/*
Name of the PVC backing /var/lib/beacon.
*/}}
{{- define "beacon.dataClaimName" -}}
{{- default (printf "%s-data" (include "beacon.fullname" .)) .Values.persistence.existingClaim }}
{{- end }}

{{/*
Validate custom CA settings. The chart can either render the custom bundle or
read it from an existing ConfigMap, but never both at the same time.
*/}}
{{- define "beacon.validateCustomCA" -}}
{{- $customCA := default (dict) .Values.customCA -}}
{{- $bundle := default "" (get $customCA "bundle") | toString | trim -}}
{{- $existingConfigMap := default "" (get $customCA "existingConfigMap") | toString | trim -}}
{{- if and $bundle $existingConfigMap -}}
{{- fail "customCA.bundle and customCA.existingConfigMap are mutually exclusive; configure only one" -}}
{{- end -}}
{{- end }}

{{/*
Return a non-empty value when custom CA trust is configured.
*/}}
{{- define "beacon.customCAEnabled" -}}
{{- include "beacon.validateCustomCA" . -}}
{{- $customCA := default (dict) .Values.customCA -}}
{{- $bundle := default "" (get $customCA "bundle") | toString | trim -}}
{{- $existingConfigMap := default "" (get $customCA "existingConfigMap") | toString | trim -}}
{{- if or $bundle $existingConfigMap -}}true{{- end -}}
{{- end }}

{{/*
Name of the ConfigMap holding only the user-provided CA certificates.
*/}}
{{- define "beacon.customCAConfigMapName" -}}
{{- $customCA := default (dict) .Values.customCA -}}
{{- $existingConfigMap := default "" (get $customCA "existingConfigMap") | toString | trim -}}
{{- default (printf "%s-custom-ca" (include "beacon.fullname" .)) $existingConfigMap -}}
{{- end }}

{{/*
Source key inside the custom CA ConfigMap. Inline bundles always use ca.crt;
existing ConfigMaps may expose the bundle under a different key.
*/}}
{{- define "beacon.customCASourceKey" -}}
{{- $customCA := default (dict) .Values.customCA -}}
{{- $existingConfigMap := default "" (get $customCA "existingConfigMap") | toString | trim -}}
{{- if $existingConfigMap -}}
{{- $key := default "" (get $customCA "existingConfigMapKey") | toString | trim -}}
{{- default "ca.crt" $key -}}
{{- else -}}ca.crt{{- end -}}
{{- end }}

{{/*
Checksum annotation for custom CA configuration. Inline bundle changes trigger a
rollout automatically. For an external ConfigMap the chart can hash only the
reference; restart pods after changing the external ConfigMap contents.
*/}}
{{- define "beacon.customCAChecksum" -}}
{{- if include "beacon.customCAEnabled" . -}}
{{- $customCA := default (dict) .Values.customCA -}}
{{- $bundle := default "" (get $customCA "bundle") | toString -}}
{{- $existingConfigMap := default "" (get $customCA "existingConfigMap") | toString | trim -}}
{{- $key := include "beacon.customCASourceKey" . -}}
{{- if $bundle -}}
checksum/custom-ca: {{ $bundle | sha256sum }}
{{- else -}}
checksum/custom-ca: {{ printf "%s:%s" $existingConfigMap $key | sha256sum }}
{{- end -}}
{{- end -}}
{{- end }}

{{/*
Environment variables used by Python/OpenSSL and Requests so every component
uses the combined system + custom trust bundle.
*/}}
{{- define "beacon.customCAEnv" -}}
{{- if include "beacon.customCAEnabled" . }}
- name: SSL_CERT_FILE
  value: /etc/beacon/ca/ca-bundle.crt
- name: REQUESTS_CA_BUNDLE
  value: /etc/beacon/ca/ca-bundle.crt
{{- end }}
{{- end }}

{{/*
Init container that copies the image system trust store and appends custom PEM
certificates. It uses the same Beacon image, so the system bundle path is
identical to the application container.
*/}}
{{- define "beacon.customCAInitContainer" -}}
{{- if include "beacon.customCAEnabled" . }}
- name: build-ca-bundle
  image: {{ include "beacon.image" . }}
  imagePullPolicy: {{ .Values.image.pullPolicy }}
  command:
    - /bin/sh
    - -ec
    - |
      if [ ! -r "$SYSTEM_CA_BUNDLE" ]; then
        echo "system CA bundle is not readable: $SYSTEM_CA_BUNDLE" >&2
        exit 1
      fi
      if [ ! -s /custom-ca/ca.crt ]; then
        echo "custom CA bundle is empty: /custom-ca/ca.crt" >&2
        exit 1
      fi
      cat "$SYSTEM_CA_BUNDLE" > /ca-work/ca-bundle.crt
      printf '\n' >> /ca-work/ca-bundle.crt
      cat /custom-ca/ca.crt >> /ca-work/ca-bundle.crt
  env:
    - name: SYSTEM_CA_BUNDLE
      {{- $systemBundlePath := default "" (get (default (dict) .Values.customCA) "systemBundlePath") | toString | trim }}
      value: {{ default "/etc/ssl/certs/ca-certificates.crt" $systemBundlePath | quote }}
  volumeMounts:
    - name: custom-ca-source
      mountPath: /custom-ca
      readOnly: true
    - name: custom-ca-bundle
      mountPath: /ca-work
{{- end }}
{{- end }}

{{/*
Volumes shared by every component.
*/}}
{{- define "beacon.volumes" -}}
- name: config
  secret:
    secretName: {{ include "beacon.configSecretName" . }}
- name: data
  {{- if .Values.persistence.enabled }}
  persistentVolumeClaim:
    claimName: {{ include "beacon.dataClaimName" . }}
  {{- else }}
  emptyDir: {}
  {{- end }}
- name: logs
  emptyDir: {}
{{- if include "beacon.customCAEnabled" . }}
- name: custom-ca-source
  configMap:
    name: {{ include "beacon.customCAConfigMapName" . }}
    items:
      - key: {{ include "beacon.customCASourceKey" . | quote }}
        path: ca.crt
- name: custom-ca-bundle
  emptyDir: {}
{{- end }}
{{- with .Values.extraVolumes }}
{{ toYaml . }}
{{- end }}
{{- end }}

{{/*
Volume mounts shared by every component.
*/}}
{{- define "beacon.volumeMounts" -}}
- name: config
  mountPath: /etc/beacon
  readOnly: true
- name: data
  mountPath: /var/lib/beacon
- name: logs
  mountPath: /var/log/beacon
{{- if include "beacon.customCAEnabled" . }}
- name: custom-ca-bundle
  mountPath: /etc/beacon/ca
  readOnly: true
{{- end }}
{{- with .Values.extraVolumeMounts }}
{{ toYaml . }}
{{- end }}
{{- end }}

{{/*
Pod annotation with the config checksum so config changes roll pods.
Empty when an existing Secret is used (the chart cannot see its content).
*/}}
{{- define "beacon.configChecksum" -}}
{{- if not .Values.existingConfigSecret -}}
checksum/config: {{ include "beacon.config" . | sha256sum }}
{{- end }}
{{- end }}
