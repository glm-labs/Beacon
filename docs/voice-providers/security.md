---
title: Voice Provider Security
description: Security recommendations for custom voice providers
---

# Voice Provider Security

Custom providers are executable Python code.

Only install providers from trusted sources.

## Directory permissions

Recommended permissions:

```bash
sudo mkdir -p /usr/local/lib/beacon/voice_providers
sudo chown root:root /usr/local/lib/beacon/voice_providers
sudo chmod 755 /usr/local/lib/beacon/voice_providers
```

The providers directory must not be writable by:

- the web server user;
- the Beacon application user;
- untrusted users;
- the Beacon UI.

## Secrets

Do not hardcode secrets in provider files.

Bad:

```python
api_token = "secret-token"
```

Good:

```json
"provider_config": {
  "api_token": "${VOICE_API_TOKEN}"
}
```

Then configure the environment variable for the Beacon service:

```bash
export VOICE_API_TOKEN="secret-token"
```

For systemd, use an environment file or service environment configuration.

Example:

```ini
Environment="VOICE_API_TOKEN=secret-token"
```

## Logging

Providers may log useful operational information, but must not log secrets or full phone numbers.

Good:

```python
import logging

logger = logging.getLogger("oncall.voice")


def mask_phone(phone):
    if not phone:
        return None

    value = str(phone)

    if len(value) <= 4:
        return "****"

    return f"***{value[-4:]}"


logger.info(
    "placing voice call",
    extra={
        "extra": {
            "provider": self.name,
            "phone": mask_phone(request.phone),
            "alert_id": request.alert_id,
            "event_type": request.event_type,
        }
    },
)
```

Bad:

```python
logger.info(f"calling {request.phone} with token {self.config['api_token']}")
```

## Callback secrets

Callback secrets should be unique and hard to guess.

Use channel-level secrets when possible:

```json
{
  "callback_secret": "long-random-secret"
}
```

Avoid short secrets:

```text
test
123
secret
change-me
```

## Provider webhook signatures

If your provider signs callbacks, validate the signature inside `parse_callback()`.

Example:

```python
def parse_callback(self, payload, headers=None, raw_body=None, query_args=None):
    signature = headers.get("X-Provider-Signature") if headers else None

    if not self._is_valid_signature(raw_body or b"", signature):
        raise RuntimeError("invalid provider callback signature")

    ...
```

## Recommended rules

```text
- The providers directory must not be writable by the web server user.
- The providers directory must not be writable from the Beacon UI.
- Provider files should be reviewed before installation.
- Secrets should be passed through environment variables.
- Provider logs must not contain API tokens, passwords or full phone numbers.
- Callback secrets should be unique and hard to guess.
- Provider-specific webhook signatures should be validated when supported.
```

Do not allow untrusted users to upload provider files.
