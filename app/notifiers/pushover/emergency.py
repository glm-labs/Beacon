"""Stop emergency Pushover pages once their alert stops firing.

An emergency (priority 2) message repeats on the phone every `retry`
seconds until that recipient taps Acknowledge or `expire` passes. Every
person paged through a notification rule gets a message of their own, so
when one of them acknowledges, the others keep ringing; and when the alert
is acknowledged in the UI, resolves at the source or is snoozed, everyone
keeps ringing, up to `expire` (an hour by default) for something that no
longer needs anyone.

Every emergency message therefore carries the tag of its alert group (see
PushoverNotifier.send), and when the group leaves `firing` this module asks
Pushover to cancel the retries of every message with that tag
(receipts/cancel_by_tag), once per app token that sent one. A tag that has
nothing left to cancel is a no-op on Pushover's side.

Cancelling is best effort: a failure is logged and recorded on the alert
timeline, and never undoes or blocks the acknowledge, resolve or snooze
that triggered it.
"""

import logging
from urllib.parse import quote, urlencode

from app.modules.db import alerts_repo, notifications_repo
from app.modules.db.models import UserNotificationDelivery
from app.services.outbound_http import safe_request
from app.settings import Config


logger = logging.getLogger("oncall.notifications")

PUSHOVER_CANCEL_BY_TAG_URL = "https://api.pushover.net/1/receipts/cancel_by_tag/{tag}.json"

EMERGENCY_TAG_PREFIX = "beacon-alert-"


def emergency_tag(group_id):
    """Return the Pushover tag carried by every emergency page of a group."""
    return f"{EMERGENCY_TAG_PREFIX}{int(group_id)}"


def _personal_emergency_sent(group_id):
    """Return True when a notification rule sent this group an emergency page."""
    deliveries = (
        UserNotificationDelivery
        .select(UserNotificationDelivery.provider_payload)
        .where(
            (UserNotificationDelivery.group == group_id)
            & (UserNotificationDelivery.method == "pushover")
            & (UserNotificationDelivery.status == "sent")
        )
    )

    return any(
        (delivery.provider_payload or {}).get("pushover_receipt")
        for delivery in deliveries
    )


def _emergency_app_tokens(group_id):
    """Return the app tokens that may have sent this group an emergency page.

    A personal delivery records the receipt Pushover returns for an
    emergency message, and always uses the app-wide token. A channel keeps
    a single record per group that later sends overwrite, so any Pushover
    channel that sent this group anything counts, with its own token.
    """
    tokens = []

    if _personal_emergency_sent(group_id):
        tokens.append(str(Config.PUSHOVER_APP_TOKEN or "").strip())

    for record in notifications_repo.list_notifications_for_group(group_id):
        channel = record.channel

        if channel.channel_type != "pushover":
            continue

        config = channel.config or {}
        tokens.append(
            str(config.get("app_token") or Config.PUSHOVER_APP_TOKEN or "").strip()
        )

    unique_tokens = []
    for token in tokens:
        if token and token not in unique_tokens:
            unique_tokens.append(token)

    return unique_tokens


def _cancel_by_tag(app_token, tag):
    response = safe_request(
        "POST",
        PUSHOVER_CANCEL_BY_TAG_URL.format(tag=quote(tag, safe="")),
        data=urlencode({"token": app_token}),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=5,
    )
    response.raise_for_status()

    body = response.json()
    if body.get("status") != 1:
        errors = body.get("errors") or ["unknown Pushover error"]
        raise RuntimeError(
            "pushover refused the cancel: " + ", ".join(str(e) for e in errors)
        )

    try:
        return int(body.get("canceled") or 0)
    except (TypeError, ValueError):
        return 0


def cancel_emergency_pages(group, reason):
    """Cancel the retries of every emergency page sent for `group`.

    `reason` names the transition ("acknowledged", "resolved", "snoozed")
    for the timeline. Returns how many messages Pushover cancelled.
    """
    tag = emergency_tag(group.id)
    cancelled = 0

    try:
        tokens = _emergency_app_tokens(group.id)
    except Exception:
        logger.exception(
            "pushover emergency cancel lookup failed",
            extra={"extra": {"alert_group_id": group.id, "reason": reason}},
        )
        return 0

    for token in tokens:
        try:
            cancelled += _cancel_by_tag(token, tag)
        except Exception as exc:
            logger.warning(
                "pushover emergency cancel failed",
                extra={
                    "extra": {
                        "alert_group_id": group.id,
                        "reason": reason,
                        "error": str(exc),
                    }
                },
            )
            alerts_repo.create_alert_event(
                group_id=group.id,
                event_type="pushover_emergency_cancel_failed",
                message=(
                    f"Could not stop the emergency Pushover pages after {reason}: "
                    f"{exc}. They repeat until acknowledged on the phone or expired."
                ),
            )

    if cancelled:
        alerts_repo.create_alert_event(
            group_id=group.id,
            event_type="pushover_emergency_cancelled",
            message=(
                f"Stopped {cancelled} emergency Pushover page(s), alert {reason}"
            ),
        )

    return cancelled
