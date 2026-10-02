"""Snooze: hold a firing alert group quiet for a set time.

A snoozed group stays ``firing``. Nobody has taken ownership of it, which is
what separates a snooze from an acknowledgement; it has only been told to
stop paging for a while. Until ``snoozed_until`` passes, the group sends no
notifications, reminders or escalations. When the time is up (or someone
wakes it by hand) it notifies again and its escalation clock restarts from
the current step, the same way it does after a maintenance window ends.

Leaving ``firing`` (acknowledge, resolve, merge) ends a snooze: the repo
clears the snooze columns on those transitions, so a group that fires again
later starts loud.
"""

import logging
from datetime import timedelta

from app.modules.common import utc_now
from app.modules.db import alerts_repo
from app.modules.db.models import AlertGroup
from app.services import escalation_policies as escalation_policy_service
from app.services.notifications.rules import cancel_pending_group_deliveries

logger = logging.getLogger("oncall.alerts")

SNOOZE_MIN_MINUTES = 5
SNOOZE_MAX_MINUTES = 7 * 24 * 60
SNOOZE_REASON_MAX_LENGTH = 500

SNOOZE_CANCELLED_DELIVERY_EVENT_TYPES = frozenset({
    "notification",
    "reminder",
    "escalation",
})


class SnoozeError(Exception):
    """The group cannot be snoozed or woken in its current state."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def is_snoozed(group, now=None):
    """Return True while the group's snooze is still running."""
    until = getattr(group, "snoozed_until", None)

    if not until or getattr(group, "status", None) != "firing":
        return False

    return until > (now or utc_now())


def snooze_alert(alert_id, *, minutes, user_id=None, reason=None):
    """Snooze a firing alert group for ``minutes``.

    Snoozing an already snoozed group moves the deadline; it does not stack.
    """
    minutes = int(minutes)

    if not SNOOZE_MIN_MINUTES <= minutes <= SNOOZE_MAX_MINUTES:
        raise SnoozeError(
            "invalid_duration",
            f"Snooze must be between {SNOOZE_MIN_MINUTES} and "
            f"{SNOOZE_MAX_MINUTES} minutes.",
        )

    group = alerts_repo.get_alert_group(alert_id)

    if group.merged_into_id or group.status != "firing":
        raise SnoozeError(
            "not_firing",
            "Only a firing alert group can be snoozed.",
        )

    now = utc_now()
    until = now + timedelta(minutes=minutes)
    reason = (reason or "").strip()[:SNOOZE_REASON_MAX_LENGTH] or None

    group = alerts_repo.set_alert_group_snooze(
        group,
        until=until,
        user_id=user_id,
        reason=reason,
        now=now,
    )

    # Work queued before the snooze would otherwise still go out.
    cancel_pending_group_deliveries(
        group,
        event_types=SNOOZE_CANCELLED_DELIVERY_EVENT_TYPES,
        reason="alert_snoozed",
    )

    alerts_repo.create_alert_event(
        group_id=group.id,
        event_type="snoozed",
        message=_snoozed_event_message(minutes, until, reason),
        user_id=user_id,
    )

    return group


def wake_alert(alert_id, *, user_id=None, expired=False):
    """End a snooze and put the group back into the paging lifecycle.

    Returns the group, or None when there was no snooze left to end (another
    worker got there first, or the group already left ``firing``).
    """
    group = alerts_repo.get_alert_group(alert_id)

    if not getattr(group, "snoozed_until", None):
        if expired:
            return None
        raise SnoozeError("not_snoozed", "This alert group is not snoozed.")

    now = utc_now()
    still_firing = group.status == "firing" and not group.merged_into_id
    next_escalation_at = None

    if still_firing and group.escalation_policy_id and group.escalation_rule_id:
        next_escalation_at = escalation_policy_service.get_next_escalation_at(
            group.escalation_rule,
            now,
        )

    if not alerts_repo.clear_alert_group_snooze(
        group,
        now=now,
        next_escalation_at=next_escalation_at,
        restart_reminders=still_firing,
    ):
        return None

    alerts_repo.create_alert_event(
        group_id=group.id,
        event_type="snooze_expired" if expired else "snooze_ended",
        message=(
            "Snooze expired; notifications resumed"
            if expired
            else "Snooze ended early; notifications resumed"
        ),
        user_id=user_id,
    )

    if still_firing:
        # Imported here: the queue imports this module to honour snoozes.
        from app.services.alerts.notification_queue import (
            schedule_group_notification,
        )

        schedule_group_notification(
            group,
            reason="snooze_expired" if expired else "snooze_ended",
            now=now,
        )

    return group


def wake_if_due(group, now=None):
    """Wake ``group`` if its snooze deadline has passed. Returns True if it did."""
    until = getattr(group, "snoozed_until", None)

    if not until or until > (now or utc_now()):
        return False

    try:
        return wake_alert(group.id, expired=True) is not None
    except Exception:
        logger.exception(
            "failed to wake snoozed alert group",
            extra={"extra": {"alert_group_id": group.id}},
        )
        return False


def _snoozed_event_message(minutes, until, reason):
    text = f"Snoozed for {_format_minutes(minutes)} until {until:%Y-%m-%d %H:%M} UTC"
    return f"{text}: {reason}" if reason else text


def _format_minutes(minutes):
    if minutes % 1440 == 0:
        days = minutes // 1440
        return f"{days} day" + ("s" if days != 1 else "")
    if minutes % 60 == 0:
        hours = minutes // 60
        return f"{hours} hour" + ("s" if hours != 1 else "")
    return f"{minutes} minutes"
