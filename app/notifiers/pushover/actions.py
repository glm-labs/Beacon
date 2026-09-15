"""Signing helpers for the Pushover acknowledge callback.

Pushover's own notification UI only ever exposes one interactive action on
an emergency-priority (2) message: a built-in Acknowledge button, wired
through the `callback` URL supplied at send time. There is no Block-Kit-style
menu of actions like Slack/Mattermost, so unlike those two, there is exactly
one action worth signing.
"""

import hashlib
import hmac


PUSHOVER_ACKNOWLEDGE_ACTION = "acknowledge"

# A shared-channel send signs a real NotificationChannel id; a personal
# notification-rule send (see app/services/notifications/rules.py,
# send_direct_notifier_delivery) has no channel row at all and signs the
# UserNotificationDelivery id instead. The two id spaces can collide, so
# `kind` is folded into the signed payload -- a signature minted for one
# kind must not verify against the other, even at the same numeric id.
PUSHOVER_TARGET_KINDS = {"channel", "delivery"}


def _action_payload(alert_id, target_id, kind):
    kind = str(kind or "").strip()
    if kind not in PUSHOVER_TARGET_KINDS:
        raise ValueError(f"unsupported Pushover callback target kind: {kind}")
    return f"ir:pushover:{PUSHOVER_ACKNOWLEDGE_ACTION}:{kind}:{int(alert_id)}:{int(target_id)}"


def build_pushover_action_signature(secret, alert_id, target_id, kind):
    """Return an HMAC signature without exposing the signing secret."""
    secret = str(secret or "")
    if not secret:
        raise ValueError("Pushover action signing secret is missing")

    payload = _action_payload(alert_id, target_id, kind)
    return hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_pushover_action_signature(secret, signature, alert_id, target_id, kind):
    """Return True when a Pushover callback signature is authentic."""
    if not secret or not signature:
        return False

    try:
        expected = build_pushover_action_signature(secret, alert_id, target_id, kind)
    except (TypeError, ValueError):
        return False

    return hmac.compare_digest(str(signature), expected)
