#!/usr/bin/env python3
"""Minimal Beacon REST API helper for the config-as-code tools.

Connection via env vars, same convention as Upgreat-AI/zabbix's own
config/services/tools/zbx_api.py:
    BEACON_API_URL    e.g. https://beacon.example.internal (no trailing /api)
    BEACON_API_TOKEN  a personal API token (Profile -> API tokens), Bearer

Deliberately stdlib-only urllib, not requests: this runs in CI, and the
whole point of the pattern this mirrors is that the tooling has no
dependencies to install beyond the interpreter itself.
"""

import json
import os
import ssl
import sys
import urllib.error
import urllib.request


def _url(path):
    base = os.environ.get("BEACON_API_URL", "http://127.0.0.1:8080").rstrip("/")
    return f"{base}{path}"


def api(method, path, body=None):
    token = os.environ.get("BEACON_API_TOKEN")
    if not token:
        sys.exit("BEACON_API_TOKEN ontbreekt in de environment")

    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        _url(path),
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )

    context = ssl.create_default_context()

    try:
        with urllib.request.urlopen(request, context=context, timeout=30) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc
