import json
from urllib.parse import quote

from app.services.severity import normalize_severity
from app.services.integrations.normalizers.common import normalize_event_link, first_non_empty, first_event_link, \
    add_event_link_label, make_dedup_key


def build_zabbix_event_link(zabbix_url, event_id=None, trigger_id=None):
    """Build Zabbix event link when frontend URL is provided."""
    zabbix_url = normalize_event_link(zabbix_url)

    if not zabbix_url or not event_id:
        return None

    base_url = zabbix_url.rstrip("/")
    event_id = quote(str(event_id))

    if trigger_id:
        trigger_id = quote(str(trigger_id))
        return f"{base_url}/tr_events.php?triggerid={trigger_id}&eventid={event_id}"

    return (
        f"{base_url}/zabbix.php?action=problem.view"
        f"&filter_set=1&filter_eventids%5B%5D={event_id}"
    )


def normalize_zabbix_status(value):
    """Convert Zabbix event status to Beacon alert status."""
    status = str(value or "").strip().lower()

    if status in {"ok", "resolved", "resolve", "recovery", "closed", "0"}:
        return "resolved"

    return "firing"


def normalize_zabbix_severity(value):
    """Map a Zabbix severity onto Beacon's own severity scale.

    Zabbix has six levels and Beacon has six, so each keeps its rank:
    Disaster -> critical, High -> high, Average -> medium, Warning ->
    warning, Information and Not classified -> info. This is the same
    alias table every other part of the app uses (app/services/severity.py).

    High used to collapse into critical, and critical is what notifiers
    treat as the top level: a Pushover channel sends it as an emergency
    page that repeats until acknowledged. Every High trigger paged like a
    Disaster, and channel filters could not tell the two apart.
    """
    return normalize_severity(value) or "info"


def normalize_zabbix_event_tag_value(value):
    """Keep raw event tag value readable for alert labels."""
    if value is None:
        return None

    if isinstance(value, str):
        value = value.strip()
        return value or None

    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(value)


def normalize_zabbix_tags(tags):
    """Normalize Zabbix tags into a flat labels dict."""
    result = {}

    if not tags:
        return result

    if isinstance(tags, dict):
        return dict(tags)

    if isinstance(tags, str):
        value = tags.strip()

        if not value:
            return result

        try:
            return normalize_zabbix_tags(json.loads(value))
        except Exception:
            # Fallback for comma-separated EVENT.TAGS-like strings.
            for item in value.split(","):
                item = item.strip()

                if not item:
                    continue

                if ":" in item:
                    key, val = item.split(":", 1)
                    result[key.strip()] = val.strip()
                else:
                    result[item] = ""

            return result

    if isinstance(tags, list):
        for item in tags:
            if not isinstance(item, dict):
                continue

            key = (
                item.get("tag")
                or item.get("name")
                or item.get("key")
            )

            if not key:
                continue

            result[str(key)] = item.get("value")

    return result


def normalize_zabbix(payload):
    """Normalize Zabbix webhook payload."""
    labels = dict(payload.get("labels") or {})

    event_tag_value = first_non_empty(
        payload.get("event_tag"),
        payload.get("event_tags"),
        labels.get("event_tag"),
    )

    if event_tag_value:
        labels.setdefault(
            "event_tag",
            normalize_zabbix_event_tag_value(event_tag_value),
        )

    labels.update(normalize_zabbix_tags(payload.get("tags")))
    labels.update(normalize_zabbix_tags(payload.get("tags_json")))
    labels.update(normalize_zabbix_tags(payload.get("event_tag")))
    labels.update(normalize_zabbix_tags(payload.get("event_tags")))

    host = first_non_empty(
        payload.get("host"),
        payload.get("host_name"),
        payload.get("hostname"),
        labels.get("host"),
        labels.get("host_name"),
        labels.get("hostname"),
    )

    event_name = first_non_empty(
        payload.get("event_name"),
        payload.get("problem_name"),
        payload.get("name"),
        labels.get("event_name"),
        labels.get("problem_name"),
    )

    trigger_name = first_non_empty(
        payload.get("trigger_name"),
        labels.get("trigger_name"),
        labels.get("trigger"),
    )

    title = first_non_empty(
        payload.get("title"),
        payload.get("subject"),
        event_name,
        trigger_name,
        labels.get("alertname"),
        "Zabbix alert",
    )

    message = first_non_empty(
        payload.get("message"),
        payload.get("description"),
        payload.get("opdata"),
        "",
    )

    if not message:
        message_parts = []

        if host:
            message_parts.append(f"Host: {host}")

        if payload.get("opdata"):
            message_parts.append(f"Operational data: {payload.get('opdata')}")

        if event_name and event_name != title:
            message_parts.append(f"Event: {event_name}")

        if trigger_name and trigger_name != title:
            message_parts.append(f"Trigger: {trigger_name}")

        message = "\n".join(message_parts)

    if host:
        labels.setdefault("host", host)

    if event_name:
        labels.setdefault("event_name", event_name)

    if trigger_name:
        labels.setdefault("trigger_name", trigger_name)

    external_id = first_non_empty(
        payload.get("event_id"),
        payload.get("eventid"),
        payload.get("trigger_id"),
        payload.get("triggerid"),
    )

    trigger_id = first_non_empty(
        payload.get("trigger_id"),
        payload.get("triggerid"),
    )

    raw_severity = first_non_empty(
        payload.get("severity"),
        payload.get("event_severity"),
        payload.get("trigger_severity"),
        labels.get("severity"),
    )

    if raw_severity:
        labels.setdefault("zabbix_severity", raw_severity)

    severity = normalize_zabbix_severity(raw_severity)

    status = normalize_zabbix_status(
        first_non_empty(
            payload.get("status"),
            payload.get("event_status"),
        )
    )

    event_link = first_event_link(
        payload.get("event_link"),
        payload.get("event_url"),
        payload.get("problem_url"),
        payload.get("trigger_url"),
        labels.get("event_link"),
        labels.get("event_url"),
        labels.get("problem_url"),
        labels.get("trigger_url"),
        build_zabbix_event_link(
            payload.get("zabbix_url"),
            event_id=first_non_empty(payload.get("event_id"), payload.get("eventid")),
            trigger_id=trigger_id,
        ),
    )

    add_event_link_label(labels, event_link)

    return [
        {
            "source": "zabbix",
            "team_slug": (
                payload.get("team")
                or labels.get("team")
                or labels.get("oncall_team")
            ),
            "external_id": external_id,
            "dedup_key": (
                    payload.get("fingerprint")
                    or make_dedup_key("zabbix", external_id, title, labels)
            ),
            "title": title,
            "message": message or "",
            "severity": severity,
            "labels": labels,
            "payload": payload,
            "status": status,
        }
    ]
