"""Pushover notifier: shared-channel delivery and personal delivery rules.

Pushover is used two ways in this app, both through this one notifier:

- as a shared "pushover" channel (NOTIFIERS registry, app/notifiers/registry.py)
  -- a team/route-level delivery target, typically a Pushover delivery
  *group* key so an on-call rotation's members all receive the page;
- as a personal notification rule (DIRECT_NOTIFIERS in
  app/services/notifications/rules.py) -- an individual's own Pushover user
  key, alongside email and voice-call as personal follow-up methods.

`channel` is a real NotificationChannel row in the first case and a
SimpleNamespace stand-in (see rules.build_direct_channel_config) in the
second -- see _callback_target_kind for why that distinction matters.

The one thing Pushover gets that Discord/Teams/generic webhook don't: on
critical alerts (Pushover priority 2, "emergency"), Pushover puts a real
Acknowledge button in the notification itself and keeps re-alerting every
`retry` seconds until someone taps it or `expire` seconds pass. Setting
`callback` on that send means tapping Acknowledge calls straight back into
this app's own acknowledge_alert() -- see app/views/integrations_view.py,
pushover_callback() -- so a Disaster-severity page can be acknowledged
without opening Beacon at all, using the exact same code path a Slack or
Mattermost button click would use.
"""

from app.modules.db.models import NotificationChannel
from app.notifiers.base import BaseNotifier
from app.notifiers.pushover.actions import build_pushover_action_signature
from app.services.alerts.priority import format_alert_title_with_priority
from app.services.links import build_alert_web_url
from app.services.outbound_http import safe_request
from app.services.severity import normalize_severity
from app.settings import Config


PUSHOVER_MESSAGES_URL = "https://api.pushover.net/1/messages.json"

# Pushover priorities range -2 (no notification, no sound/vibration) to 2
# (emergency: bypasses quiet hours, repeats until acknowledged or expired).
# Keyed by the app's own normalized severities (app/services/severity.py),
# so this stays in the same vocabulary as channel notify_on_severities
# filtering and every other severity-aware piece of the app.
DEFAULT_PRIORITY_MAP = {
    "critical": 2,
    "high": 1,
    "medium": 0,
    "warning": 0,
    "low": -1,
    "info": -1,
}

# An acknowledged/resolved update is news, not a page: send it quietly,
# never re-triggering emergency behavior for something that is being (or
# already was) handled.
LIFECYCLE_UPDATE_PRIORITY = -1

MAX_TITLE = 250
MAX_MESSAGE = 1024


def _clip(value, limit):
    text = "" if value is None else str(value)
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


class PushoverNotifier(BaseNotifier):
    """Send alert notifications through the Pushover API."""

    name = "pushover"

    def send(self, channel, alert, text, event_type="notification"):
        config = channel.config or {}

        app_token = str(
            config.get("app_token") or Config.PUSHOVER_APP_TOKEN or ""
        ).strip()
        if not app_token:
            raise RuntimeError("pushover app_token is missing")

        target = str(config.get("target") or "").strip()
        if not target:
            raise RuntimeError("pushover target is missing")

        priority = self._priority_for(config, alert, event_type)

        payload = {
            "token": app_token,
            "user": target,
            "title": _clip(self._title_for(alert, event_type), MAX_TITLE),
            "message": _clip(text, MAX_MESSAGE),
            "priority": priority,
        }

        alert_url = build_alert_web_url(alert)
        if alert_url:
            payload["url"] = alert_url
            payload["url_title"] = "Open in Beacon"

        if priority == 2:
            payload["retry"] = self._retry_seconds(config)
            payload["expire"] = self._expire_seconds(config)

            callback_url = self._callback_url(channel, alert)
            if callback_url:
                payload["callback"] = callback_url

        response = safe_request(
            "POST",
            PUSHOVER_MESSAGES_URL,
            json=payload,
            timeout=10,
        )
        response.raise_for_status()

        body = response.json()
        if body.get("status") != 1:
            errors = body.get("errors") or ["unknown Pushover error"]
            raise RuntimeError(
                "pushover rejected the message: " + ", ".join(str(e) for e in errors)
            )

        return {
            "provider": self.name,
            "provider_status": "sent",
            "provider_payload": {"pushover_request_id": body.get("request")},
        }

    def _title_for(self, alert, event_type):
        title = format_alert_title_with_priority(alert)
        if event_type == "resolved":
            return f"RESOLVED: {title}"
        if event_type == "acknowledged":
            return f"ACKNOWLEDGED: {title}"
        return title

    def _priority_for(self, config, alert, event_type):
        if event_type in {"resolved", "acknowledged"}:
            return LIFECYCLE_UPDATE_PRIORITY

        priority_map = dict(DEFAULT_PRIORITY_MAP)
        priority_map.update(config.get("priority_map") or {})

        severity = normalize_severity(getattr(alert, "severity", None))

        try:
            priority = int(priority_map.get(severity, 0))
        except (TypeError, ValueError):
            priority = 0

        return max(-2, min(2, priority))

    def _retry_seconds(self, config):
        try:
            value = int(config.get("retry_seconds") or Config.PUSHOVER_RETRY_SECONDS)
        except (TypeError, ValueError):
            value = Config.PUSHOVER_RETRY_SECONDS
        # Pushover rejects a retry below 30s on a priority-2 message.
        return max(30, value)

    def _expire_seconds(self, config):
        try:
            value = int(config.get("expire_seconds") or Config.PUSHOVER_EXPIRE_SECONDS)
        except (TypeError, ValueError):
            value = Config.PUSHOVER_EXPIRE_SECONDS
        # Pushover caps expire at 10800s (3h) on a priority-2 message.
        return min(10800, max(30, value))

    def _action_secret(self, channel):
        config = channel.config or {}
        return config.get("callback_secret") or Config.PUSHOVER_ACTION_SECRET

    def _callback_target_kind(self, channel):
        """Return whether `channel` is a real channel row or a rule delivery.

        A shared "pushover" channel and a personal notification-rule
        delivery both reach this notifier, and both need a callback URL
        that survives the round trip to Pushover and back -- see the
        module docstring. isinstance is the deliberate way to tell them
        apart: a personal delivery is a SimpleNamespace stand-in built by
        rules.build_direct_channel_config, never a real model row.
        """
        return "channel" if isinstance(channel, NotificationChannel) else "delivery"

    def _callback_url(self, channel, alert):
        secret = self._action_secret(channel)
        if not secret:
            return None

        kind = self._callback_target_kind(channel)
        signature = build_pushover_action_signature(secret, alert.id, channel.id, kind)
        base = Config.PUBLIC_BASE_URL.rstrip("/")

        return (
            f"{base}/api/integrations/pushover/callback"
            f"?kind={kind}&alert_id={alert.id}&target_id={channel.id}"
            f"&signature={signature}"
        )
