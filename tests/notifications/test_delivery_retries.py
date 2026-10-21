from datetime import timedelta

import pytest

from app.modules.common import utc_now
from app.modules.db.models import AlertEvent, UserNotificationDelivery
from app.services.alerts.actions import acknowledge_alert
from app.services.alerts.lifecycle import upsert_alert
from app.services.notifications import rules
from tests.factories import add_user_to_team, create_group, create_route, create_team, create_user


class FlakyNotifier:
    """Fails the first `failures` sends, then succeeds."""

    def __init__(self, failures, error="outbound hostname resolution failed"):
        self.failures = failures
        self.error = error
        self.calls = 0

    def send(self, channel, alert_group, text, event_type="notification"):
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError(self.error)
        return {"provider": "pushover", "provider_status": "sent"}


@pytest.fixture
def retries(monkeypatch):
    monkeypatch.setattr(rules.Config, "NOTIFICATION_DELIVERY_RETRIES", 3)
    monkeypatch.setattr(rules.Config, "NOTIFICATION_DELIVERY_RETRY_SECONDS", 30)


def _paged_user_and_group(username):
    group = create_group()
    team = create_team(group)
    user = create_user(username, group)
    add_user_to_team(team, user, role="responder")
    route = create_route(team, group_by=["alertname", "instance"])
    result = upsert_alert({
        "source": "alertmanager",
        "forced_route_id": route.id,
        "external_id": f"external-{username}",
        "dedup_key": f"dedup-{username}",
        "title": "SiteDown",
        "message": "docs is unreachable",
        "severity": "critical",
        "labels": {"alertname": "SiteDown", "instance": "docs"},
        "payload": {},
        "status": "firing",
    })
    alert_group = result.group
    alert_group.assignee = user
    alert_group.save()
    return user, alert_group


def _due_pushover_delivery(user, alert_group):
    return UserNotificationDelivery.create(
        group=alert_group.id,
        user=user.id,
        rule=None,
        method=rules.NOTIFICATION_METHOD_PUSHOVER,
        event_type="notification",
        status="pending",
        scheduled_at=utc_now() - timedelta(seconds=1),
    )


def _make_due(delivery):
    (
        UserNotificationDelivery
        .update(scheduled_at=utc_now() - timedelta(seconds=1))
        .where(UserNotificationDelivery.id == delivery.id)
        .execute()
    )


def _events(alert_group, event_type):
    return [
        event.message
        for event in AlertEvent.select().where(
            (AlertEvent.group == alert_group.id)
            & (AlertEvent.event_type == event_type)
        ).order_by(AlertEvent.id)
    ]


def test_a_failed_page_is_tried_again_later(retries, db, monkeypatch):
    user, alert_group = _paged_user_and_group("retry-later")
    delivery = _due_pushover_delivery(user, alert_group)
    notifier = FlakyNotifier(failures=1)
    monkeypatch.setitem(rules.DIRECT_NOTIFIERS, rules.NOTIFICATION_METHOD_PUSHOVER, notifier)

    before = utc_now()
    assert rules.process_due_user_notifications() == 0

    stored = UserNotificationDelivery.get_by_id(delivery.id)
    assert stored.status == "pending"
    assert stored.attempts == 1
    assert stored.last_error == "outbound hostname resolution failed"
    assert before + timedelta(seconds=29) <= stored.scheduled_at <= utc_now() + timedelta(seconds=31)
    assert _events(alert_group, "notification_pushover_retry") == [
        "pushover to retry-later failed (attempt 1 of 4): "
        "outbound hostname resolution failed. Trying again in 30 s."
    ]

    # Not due yet: nothing is sent again.
    assert rules.process_due_user_notifications() == 0
    assert notifier.calls == 1

    _make_due(stored)
    assert rules.process_due_user_notifications() == 1

    stored = UserNotificationDelivery.get_by_id(delivery.id)
    assert stored.status == "sent"
    assert stored.sent_at is not None
    assert stored.attempts == 2
    assert stored.last_error is None


def test_the_wait_doubles_and_the_page_is_given_up_after_the_last_retry(retries, db, monkeypatch):
    user, alert_group = _paged_user_and_group("retry-give-up")
    delivery = _due_pushover_delivery(user, alert_group)
    notifier = FlakyNotifier(failures=10, error="outbound HTTP request returned status 503")
    monkeypatch.setitem(rules.DIRECT_NOTIFIERS, rules.NOTIFICATION_METHOD_PUSHOVER, notifier)

    waits = []
    for _ in range(3):
        before = utc_now()
        rules.process_due_user_notifications()
        stored = UserNotificationDelivery.get_by_id(delivery.id)
        assert stored.status == "pending"
        waits.append(round((stored.scheduled_at - before).total_seconds()))
        _make_due(stored)

    assert waits == [30, 60, 120]

    rules.process_due_user_notifications()

    stored = UserNotificationDelivery.get_by_id(delivery.id)
    assert stored.status == "failed"
    assert stored.attempts == 4
    assert notifier.calls == 4
    assert _events(alert_group, "notification_pushover_failed") == [
        "pushover to retry-give-up failed after 4 attempt(s), giving up: "
        "outbound HTTP request returned status 503"
    ]

    # A failed delivery is never picked up again.
    assert rules.process_due_user_notifications() == 0
    assert notifier.calls == 4


def test_an_acknowledge_cancels_the_retries_left(retries, db, monkeypatch):
    user, alert_group = _paged_user_and_group("retry-acked")
    delivery = _due_pushover_delivery(user, alert_group)
    notifier = FlakyNotifier(failures=1)
    monkeypatch.setitem(rules.DIRECT_NOTIFIERS, rules.NOTIFICATION_METHOD_PUSHOVER, notifier)

    rules.process_due_user_notifications()
    acknowledge_alert(alert_group.id, user_id=user.id)

    stored = UserNotificationDelivery.get_by_id(delivery.id)
    assert stored.status == "skipped"
    assert stored.last_error == "alert_acknowledged"

    _make_due(stored)
    assert rules.process_due_user_notifications() == 0
    assert notifier.calls == 1


def test_an_immediate_page_that_fails_is_retried_by_the_scheduler(retries, db, monkeypatch):
    user, alert_group = _paged_user_and_group("retry-immediate")
    user.pushover_user_key = "uIMMEDIATE"
    user.save()
    rules.create_user_rule(
        user,
        method=rules.NOTIFICATION_METHOD_PUSHOVER,
        delay_seconds=0,
        severities=["critical"],
        event_types=["notification"],
    )
    notifier = FlakyNotifier(failures=1)
    monkeypatch.setitem(rules.DIRECT_NOTIFIERS, rules.NOTIFICATION_METHOD_PUSHOVER, notifier)

    assert rules.enqueue_user_notifications(alert_group, event_type="notification") == 0

    delivery = UserNotificationDelivery.get(
        (UserNotificationDelivery.group == alert_group.id)
        & (UserNotificationDelivery.method == rules.NOTIFICATION_METHOD_PUSHOVER)
    )
    assert delivery.status == "pending"
    assert delivery.attempts == 1

    _make_due(delivery)
    assert rules.process_due_user_notifications() == 1
    assert UserNotificationDelivery.get_by_id(delivery.id).status == "sent"


def test_retries_off_fails_on_the_first_error(db, monkeypatch):
    monkeypatch.setattr(rules.Config, "NOTIFICATION_DELIVERY_RETRIES", 0)
    user, alert_group = _paged_user_and_group("retry-off")
    delivery = _due_pushover_delivery(user, alert_group)
    monkeypatch.setitem(
        rules.DIRECT_NOTIFIERS,
        rules.NOTIFICATION_METHOD_PUSHOVER,
        FlakyNotifier(failures=1),
    )

    rules.process_due_user_notifications()

    stored = UserNotificationDelivery.get_by_id(delivery.id)
    assert stored.status == "failed"
    assert stored.attempts == 1
    assert _events(alert_group, "notification_pushover_failed") == [
        "pushover to retry-off failed after 1 attempt(s), giving up: "
        "outbound hostname resolution failed"
    ]
