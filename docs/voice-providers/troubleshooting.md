---
title: Voice Provider Troubleshooting
description: Common custom voice provider problems
---

# Voice Provider Troubleshooting

## Provider not found

Error example:

```text
voice provider not found: mango
```

Check:

```text
- File exists: /usr/local/lib/beacon/voice_providers/mango.py
- Channel config has: "provider": "mango"
- File name contains only letters, numbers and underscore
- Beacon was restarted after adding the file
```

## Provider class is missing

Error example:

```text
voice provider mango must define Provider(BaseVoiceProvider)
```

Check that your module contains:

```python
class Provider(BaseVoiceProvider):
    ...
```

The class name must be exactly:

```text
Provider
```

## Config field is missing

Error example:

```text
mango config requires: api_url, api_token
```

Check `provider_config` in channel config.

## API token is empty

If you use:

```json
"api_token": "${VOICE_API_TOKEN}"
```

Check that the environment variable exists for the Beacon process.

For systemd:

```bash
sudo systemctl show beacon --property=Environment
```

Or check your service unit / environment file.

## Calls are not sent for real alerts

Check:

```text
- Alert status is firing.
- Alert severity is listed in notify_on_severities.
- Alert has an assignee with phone number.
- Channel is enabled.
- Route points to the voice channel.
```

## Callback is rejected

Check:

```text
- Callback URL contains the correct channel_id.
- Callback URL contains the correct callback secret.
- Channel type is voice_call.
- Channel config has the expected provider.
- Provider sends JSON or form data supported by parse_callback().
```

## DTMF does not acknowledge or resolve the alert

Check:

```text
- Provider sends event_type=dtmf or equivalent data that parse_callback() maps to dtmf.
- Provider sends digit.
- Channel config dtmf_actions contains this digit.
- The digit maps to acknowledge or resolve.
- call_id matches the original VoiceCallResult.call_id.
```

## Notification not found for callback

Check:

```text
- Provider returned call_id from place_call().
- Provider sends the same call_id in callbacks.
- Beacon stored external_message_id for the notification.
- Callback is sent to the same channel_id that created the call.
```

## Provider request hangs

Check:

```text
- All HTTP requests have timeouts.
- Provider API endpoint is reachable from Beacon.
- DNS resolution works.
- Firewall allows outbound provider traffic.
```

Good:

```python
requests.post(url, json=payload, timeout=10)
```

Bad:

```python
requests.post(url, json=payload)
```

## Testing checklist

Before enabling a provider in production:

```text
1. Create a test voice channel.
2. Set test_phone.
3. Configure only one test severity, for example critical.
4. Trigger a test notification.
5. Check Beacon logs.
6. Check provider-side logs or dashboard.
7. Confirm that call_id is returned.
8. Confirm that call status callbacks are received.
9. Confirm that DTMF callback with digit 1 acknowledges the alert.
10. Confirm that DTMF callback with digit 2 resolves the alert.
11. Confirm that provider errors are visible in Beacon logs.
12. Confirm that secrets and full phone numbers are not logged.
13. Enable the provider for real alert routes.
```
