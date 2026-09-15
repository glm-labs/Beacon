"""Write a Beacon acknowledge back to the Zabbix event it came from.

app/services/integrations/normalizers/zabbix.py is intake-only: Zabbix pushes
problem/recovery events in, and nothing ever flows back out. Left that way,
acknowledging a Zabbix-sourced alert in Beacon (a Slack button, the Pushover
callback, the UI, anything) does nothing on the Zabbix side -- the event
stays unacknowledged there, so Zabbix's own escalation and, on
emergency-priority Pushover sends, Pushover's own retry-until-ack keep
nagging as if nobody had looked at it. This closes that loop.

Config lives on the route, not this module: AlertRoute.integration_config
(app/modules/db/models.py) already carries per-source config for other
integrations (see app/services/integrations/sentry.py for the same pattern
with a different source). A route's `zabbix` sub-object:

    {
      "zabbix": {
        "ack_writeback_enabled": true,
        "api_url": "http://zabbix-web.zabbix.svc.cluster.local",
        "api_token": "..."
      }
    }

ack_writeback_enabled defaults to false: writing to an external system's
API is a new side effect a route shouldn't get silently just by being
named "zabbix", and api_url is very often a private/internal address that
also needs adding to Config.OUTBOUND_HTTP_PRIVATE_NETWORK_ALLOWLIST (see
app/services/outbound_http.py) before safe_request will even attempt it.
"""

import logging

from app.modules.db import alerts_repo
from app.services.outbound_http import safe_request


logger = logging.getLogger("oncall.integrations.zabbix")

# Zabbix event.acknowledge action bitmask: 0x02 acknowledge + 0x04 add
# message. Deliberately not 0x01 (close) or 0x08 (change severity) --
# a Beacon acknowledge means "someone is on it," not "this is resolved."
# Zabbix's own resolution (the trigger clearing) is what closes the
# problem; Beacon's resolve_alert() has no Zabbix-side equivalent to write
# back to, since a resolve here just means Beacon considers the incident
# handled, not that the underlying condition is gone.
ZABBIX_ACK_ACTION = 0x02 | 0x04
ZABBIX_ACK_MESSAGE = "Acknowledged via Beacon"


def _latest_external_id(group):
    """Return the Zabbix eventid of the most recent alert in this group."""
    alerts = alerts_repo.list_alerts_for_group(group.id)
    for alert in reversed(alerts):
        if alert.external_id:
            return alert.external_id
    return None


def acknowledge_upstream(group, user):
    """Acknowledge the originating Zabbix event, if writeback is configured.

    Best-effort and silent by design: called from
    app/services/alerts/actions.py right after Beacon's own acknowledge
    already committed, so a Zabbix-side failure here must never look like
    the Beacon acknowledge itself failed. Errors are logged, not raised --
    see app/services/integrations/writebacks/registry.py, which is the
    only caller and already treats every writeback this defensively, but
    this module doesn't rely on that: it catches its own errors too, so it
    stays safe to call directly (a management command, a test) as well.
    """
    route = getattr(group, "route", None)
    if not route:
        return

    config = (route.integration_config or {}).get("zabbix") or {}
    if not config.get("ack_writeback_enabled"):
        return

    api_url = str(config.get("api_url") or "").strip().rstrip("/")
    api_token = str(config.get("api_token") or "").strip()

    if not api_url or not api_token:
        logger.warning(
            "zabbix ack writeback enabled without api_url/api_token",
            extra={"extra": {"alert_group_id": group.id, "route_id": route.id}},
        )
        return

    eventid = _latest_external_id(group)
    if not eventid:
        logger.info(
            "zabbix ack writeback skipped: no Zabbix eventid on this group",
            extra={"extra": {"alert_group_id": group.id}},
        )
        return

    message = ZABBIX_ACK_MESSAGE
    if user is not None:
        message = f"{message} by {user.display_name or user.username}"

    payload = {
        "jsonrpc": "2.0",
        "method": "event.acknowledge",
        "params": {
            "eventids": [str(eventid)],
            "action": ZABBIX_ACK_ACTION,
            "message": message,
        },
        "auth": api_token,
        "id": 1,
    }

    try:
        response = safe_request(
            "POST",
            f"{api_url}/api_jsonrpc.php",
            json=payload,
            headers={"Content-Type": "application/json-rpc"},
            timeout=10,
        )
        response.raise_for_status()
        body = response.json()

        if "error" in body:
            raise RuntimeError(
                body["error"].get("data") or body["error"].get("message") or "unknown Zabbix API error"
            )
    except Exception as exc:  # noqa: BLE001 - a writeback failure must not fail the ack
        logger.warning(
            "zabbix ack writeback failed",
            extra={
                "extra": {
                    "alert_group_id": group.id,
                    "route_id": route.id,
                    "zabbix_eventid": eventid,
                    "error": str(exc)[:500],
                }
            },
        )
        return

    logger.info(
        "zabbix ack writeback succeeded",
        extra={
            "extra": {
                "alert_group_id": group.id,
                "route_id": route.id,
                "zabbix_eventid": eventid,
            }
        },
    )
