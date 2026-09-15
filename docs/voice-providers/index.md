---
title: Custom Voice Providers
description: Overview of Beacon custom voice providers
---

# Custom Voice Providers

Beacon can load custom Python voice providers for self-hosted installations.

A voice provider is a Python module that knows how to place a phone call through a specific provider API: Mango, Voximplant, Zadarma, Asterisk gateway, internal PBX, or any other service.

Beacon itself does not need to know provider-specific API details. It loads your provider module and communicates with it through a stable provider API.

## Supported features

The provider API is designed for:

- Text-to-speech calls
- Provider call ID tracking
- Call status callbacks
- DTMF button callbacks
- ACK / Resolve actions from phone keypad
- Optional call status polling

## Directory layout

Default custom providers directory:

```text
/usr/local/lib/beacon/voice_providers
```

Example:

```text
/usr/local/lib/beacon/voice_providers/
├── README.md
├── mango.py
├── zadarma.py
└── internal_pbx.py
```

Only server administrators should be able to write to this directory, because provider files are executable Python code.

Recommended permissions:

```bash
sudo mkdir -p /usr/local/lib/beacon/voice_providers
sudo chown root:root /usr/local/lib/beacon/voice_providers
sudo chmod 755 /usr/local/lib/beacon/voice_providers
```

## Documentation sections

- [Provider API](provider-api.md)
- [Configuration](configuration.md)
- [Callbacks and DTMF](callbacks.md)
- [Security](security.md)
- [Troubleshooting](troubleshooting.md)

## Examples

Example provider files are stored in:

```text
examples/voice_providers/
```

Recommended start:

```text
examples/voice_providers/example_http.py
```
