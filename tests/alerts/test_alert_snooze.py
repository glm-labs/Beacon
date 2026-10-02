from datetime import timedelta

import pytest

from app.modules.common import utc_now
from app.modules.db.models import AlertEvent, AlertGroup
from app.services.alerts import notification_queue, reminders as alert_reminders
from app.services.alerts.actions import acknowledge_alert, resolve_alert
from app.services.alerts.lifecycle import upsert_alert
from app.services.alerts.snooze import (
    SnoozeError,
    is_snoozed,
    snooze_alert,
    wake_alert,
)
from tests.factories import create_group, create_rotation, create_route, create_team


def _firing_group(name="DiskFull", *, rotation=False):
    group = create_group()
    team = create_team(group)
    route = create_route(
        team,
        source="alertmanager",
        rotation=create_rotation(team) if rotation else None,
        group_by=["alertname"],
    )
    result = upsert_alert(
        {
            "source": "alertmanager",
            "forced_route_id": route.id,
            "external_id": f"snooze-{name}",
            "dedup_key": f"snooze-{name}",
            "title": name,
            "message": f"{name} on host1",
            "severity": "critical",
            "labels": {"alertname": name, "severity": "critical", "instance": "host1"},
            "payload": {},
            "status": "firing",
        }
    )
    return AlertGroup.get_by_id(result.group.id)


def _events(group_id, event_type):
    return list(
        AlertEvent.select().where(
            (AlertEvent.group == group_id) & (AlertEvent.event_type == event_type)
        )
    )


def _expire(group_id):
    AlertGroup.update(snoozed_until=utc_now() - timedelta(seconds=1)).where(
        AlertGroup.id == group_id
    ).execute()


def test_snooze_holds_firing_group_and_drops_queued_work(db):
    group = _firing_group("SnoozeBasic")
    group.notification_pending = True
    group.notification_due_at = utc_now()
    group.notification_reason = "notification"
    group.save()

    snoozed = snooze_alert(group.id, minutes=60, reason="vendor fix at 14:00")

    stored = AlertGroup.get_by_id(group.id)
    assert stored.status == "firing"
    assert is_snoozed(stored)
    assert stored.snooze_reason == "vendor fix at 14:00"
    assert stored.notification_pending is False
    assert stored.next_escalation_at is None
    assert snoozed.snoozed_until > utc_now() + timedelta(minutes=59)
    assert len(_events(group.id, "snoozed")) == 1


def test_only_firing_groups_can_be_snoozed(db):
    group = _firing_group("SnoozeAcked")
    acknowledge_alert(group.id)

    with pytest.raises(SnoozeError) as exc:
        snooze_alert(group.id, minutes=30)

    assert exc.value.code == "not_firing"


@pytest.mark.parametrize("minutes", [0, 4, 7 * 24 * 60 + 1])
def test_snooze_length_is_bounded(db, minutes):
    group = _firing_group(f"SnoozeBounds{minutes}")

    with pytest.raises(SnoozeError) as exc:
        snooze_alert(group.id, minutes=minutes)

    assert exc.value.code == "invalid_duration"


def test_snoozed_group_gets_no_reminder_and_wakes_when_due(db, monkeypatch):
    group = _firing_group("SnoozeReminder", rotation=True)
    group.last_notification_at = utc_now() - timedelta(hours=1)
    group.save()
    snooze_alert(group.id, minutes=30)

    monkeypatch.setattr(
        alert_reminders,
        "notify_alert",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("a snoozed group must not be reminded")
        ),
    )

    assert alert_reminders.send_unacked_reminders() == 0
    assert is_snoozed(AlertGroup.get_by_id(group.id))

    _expire(group.id)
    alert_reminders.send_unacked_reminders()

    woken = AlertGroup.get_by_id(group.id)
    assert not is_snoozed(woken)
    assert woken.snoozed_until is None
    assert woken.notification_pending is True
    assert woken.notification_reason == "snooze_expired"
    assert woken.reminder_count == 0
    assert len(_events(group.id, "snooze_expired")) == 1


def test_due_notification_is_not_sent_while_snoozed(db, monkeypatch):
    group = _firing_group("SnoozeDue")
    snooze_alert(group.id, minutes=30)
    AlertGroup.update(
        notification_pending=True,
        notification_due_at=utc_now() - timedelta(seconds=1),
        notification_reason="update",
    ).where(AlertGroup.id == group.id).execute()

    sent = []
    monkeypatch.setattr(
        notification_queue,
        "notify_alert",
        lambda group, event_type="notification": sent.append(event_type) or 1,
    )

    result = notification_queue.process_due_alert_group_notifications()

    assert sent == []
    assert result["skipped"] == 1
    assert AlertGroup.get_by_id(group.id).notification_pending is False


def test_new_child_alert_does_not_break_snooze(db):
    group = _firing_group("SnoozeNewChild")
    snooze_alert(group.id, minutes=30)

    notification_queue.schedule_group_notification(AlertGroup.get_by_id(group.id))

    stored = AlertGroup.get_by_id(group.id)
    assert is_snoozed(stored)
    assert stored.notification_pending is False


def test_wake_ends_snooze_early_and_schedules_notification(db):
    group = _firing_group("SnoozeWake")
    snooze_alert(group.id, minutes=120)

    wake_alert(group.id)

    stored = AlertGroup.get_by_id(group.id)
    assert stored.snoozed_until is None
    assert stored.notification_pending is True
    assert stored.notification_reason == "snooze_ended"
    assert len(_events(group.id, "snooze_ended")) == 1

    with pytest.raises(SnoozeError) as exc:
        wake_alert(group.id)
    assert exc.value.code == "not_snoozed"


@pytest.mark.parametrize("action", [acknowledge_alert, resolve_alert])
def test_leaving_firing_clears_the_snooze(db, action):
    group = _firing_group(f"SnoozeClear{action.__name__}")
    snooze_alert(group.id, minutes=60)

    action(group.id)

    stored = AlertGroup.get_by_id(group.id)
    assert stored.snoozed_until is None
    assert stored.snoozed_by_id is None
    assert not is_snoozed(stored)


def test_snooze_api_round_trip_and_filter(client, admin_headers, db):
    group = _firing_group("SnoozeApi")
    other = _firing_group("SnoozeApiOther")

    response = client.post(
        f"/api/alerts/{group.id}/snooze",
        json={"minutes": 45, "reason": "deploy in progress"},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.get_json()
    body = response.get_json()
    assert body["snoozed"] is True
    assert body["snooze_reason"] == "deploy in progress"
    assert body["snoozed_until"]

    only_snoozed = client.get("/api/alerts?snoozed=1&page_size=100", headers=admin_headers)
    ids = {item["id"] for item in only_snoozed.get_json()["items"]}
    assert group.id in ids and other.id not in ids

    not_snoozed = client.get("/api/alerts?snoozed=0&page_size=100", headers=admin_headers)
    ids = {item["id"] for item in not_snoozed.get_json()["items"]}
    assert other.id in ids and group.id not in ids

    response = client.delete(f"/api/alerts/{group.id}/snooze", headers=admin_headers)
    assert response.status_code == 200
    assert response.get_json()["snoozed"] is False

    response = client.delete(f"/api/alerts/{group.id}/snooze", headers=admin_headers)
    assert response.status_code == 409


def test_snooze_api_validates_input(client, admin_headers, db):
    group = _firing_group("SnoozeApiInvalid")

    too_long = client.post(
        f"/api/alerts/{group.id}/snooze",
        json={"minutes": 100000},
        headers=admin_headers,
    )
    assert too_long.status_code == 400

    resolve_alert(group.id)
    not_firing = client.post(
        f"/api/alerts/{group.id}/snooze",
        json={"minutes": 30},
        headers=admin_headers,
    )
    assert not_firing.status_code == 409
    assert not_firing.get_json()["error"] == "not_firing"
