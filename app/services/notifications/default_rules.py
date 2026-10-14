"""App-wide default notification rules from beacon.conf.

A user who never created a notification rule of their own gets these
instead of only the implicit browser push, so being paged does not depend
on every responder hand-crafting rules in their profile. They are a JSON
list under [notifications] default_rules; each entry has the fields of a
personal rule:

    [notifications]
    default_rules = [{"method": "pushover", "delay_seconds": 0, "severities": ["critical", "high"]}]

Users with at least one rule of their own are never affected.

This module only parses and validates. It imports nothing from the
notifiers or the models, because app.settings calls it while the Config
class is still being built.
"""

from dataclasses import dataclass, field

from app.services.severity import SEVERITY_ALIASES, normalize_severity

# Same values as NOTIFICATION_RULE_METHODS and the rule event types in
# app.services.notifications.rules, which cannot be imported from here
# (see the module docstring). tests/notifications/test_default_rules.py
# keeps them in step.
ALLOWED_DEFAULT_RULE_METHODS = frozenset({
    "browser_push",
    "email",
    "voice_call",
    "pushover",
})

ALLOWED_DEFAULT_RULE_EVENT_TYPES = frozenset({
    "notification",
    "reminder",
    "escalation",
    "acknowledged",
    "resolved",
})

KNOWN_SEVERITIES = frozenset(SEVERITY_ALIASES.values())

DEFAULT_RULE_FIELDS = frozenset({
    "method",
    "delay_seconds",
    "severities",
    "event_types",
})


@dataclass
class DefaultNotificationRule:
    """One configured default rule.

    Has the attributes rule matching reads from a UserNotificationRule, so
    both go through the same rule_matches_group().
    """

    position: int
    method: str
    delay_seconds: int = 0
    severities: list = field(default_factory=list)
    event_types: list = field(default_factory=list)
    enabled: bool = True

    def to_dict(self):
        return {
            "position": self.position,
            "method": self.method,
            "delay_seconds": self.delay_seconds,
            "severities": list(self.severities),
            "event_types": list(self.event_types),
        }


def _config_error(message):
    return RuntimeError(f"invalid setting [notifications] default_rules: {message}")


def _string_list(item, name, position):
    values = item.get(name, [])

    if values is None:
        return []

    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        raise _config_error(f"rule {position}: {name} must be a list of strings")

    return values


def parse_default_notification_rules(raw):
    """Return validated default rules from the decoded JSON setting.

    Raises RuntimeError naming the rule at fault, so a typo stops the
    service at startup instead of quietly paging nobody. An absent or
    empty setting returns [] and keeps the old browser-push-only default.
    """

    if raw in (None, "", []):
        return []

    if not isinstance(raw, list):
        raise _config_error("must be a JSON list of rules")

    rules = []

    for position, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise _config_error(f"rule {position} must be a JSON object")

        unknown = set(item) - DEFAULT_RULE_FIELDS

        if unknown:
            raise _config_error(
                f"rule {position}: unknown field(s) " + ", ".join(sorted(unknown))
            )

        method = item.get("method")

        if method not in ALLOWED_DEFAULT_RULE_METHODS:
            raise _config_error(
                f"rule {position}: method must be one of "
                + ", ".join(sorted(ALLOWED_DEFAULT_RULE_METHODS))
            )

        delay_seconds = item.get("delay_seconds", 0)

        if (
            isinstance(delay_seconds, bool)
            or not isinstance(delay_seconds, int)
            or delay_seconds < 0
        ):
            raise _config_error(
                f"rule {position}: delay_seconds must be a whole number of seconds, 0 or more"
            )

        severities = []

        for value in _string_list(item, "severities", position):
            severity = normalize_severity(value)

            if severity not in KNOWN_SEVERITIES:
                raise _config_error(f"rule {position}: unknown severity {value!r}")

            if severity not in severities:
                severities.append(severity)

        event_types = _string_list(item, "event_types", position)
        invalid_event_types = set(event_types) - ALLOWED_DEFAULT_RULE_EVENT_TYPES

        if invalid_event_types:
            raise _config_error(
                f"rule {position}: unknown event type(s) "
                + ", ".join(sorted(invalid_event_types))
            )

        rules.append(DefaultNotificationRule(
            position=position,
            method=method,
            delay_seconds=delay_seconds,
            severities=severities,
            event_types=list(dict.fromkeys(event_types)),
        ))

    return rules
