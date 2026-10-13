"""Escalation rules that page the whole policy team at once."""

from datetime import timedelta

import app.services.alerts.escalation as alert_escalation
import app.services.alerts.notification_queue as notification_queue
from app.modules.common import utc_now
from app.modules.db.models import AlertEvent, AlertGroup, UserNotificationDelivery, UserNotificationRule
from app.services.alerts.actions import acknowledge_alert
from app.services.alerts.escalation import maybe_escalate_alert
from app.services.alerts.lifecycle import upsert_alert
from app.services.notifications import rules
from app.settings import Config
from tests.factories import (
    add_user_to_team,
    create_escalation_policy,
    create_escalation_policy_rule,
    create_group,
    create_route,
    create_rotation,
    create_team,
    create_user,
    unique,
)


def normalized_alert(**overrides):
    data = {
        "source": "alertmanager",
        "team_slug": "sre",
        "external_id": unique("external"),
        "dedup_key": unique("dedup"),
        "title": "Datacenter unreachable",
        "message": "core switch down",
        "severity": "critical",
        "labels": {"alertname": "DatacenterDown", "severity": "critical", "team": "sre"},
        "payload": {"source": "test"},
        "status": "firing",
    }
    data.update(overrides)
    return data


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"status": 1, "request": "abc", "receipt": "r1"}


def capture_pushover(monkeypatch):
    sent = []

    def fake_request(method, url, *, json, timeout):
        sent.append(json["user"])
        return FakeResponse()

    monkeypatch.setattr("app.notifiers.pushover.notifier.safe_request", fake_request)
    monkeypatch.setattr(Config, "PUSHOVER_APP_TOKEN", "app-token")
    return sent


def pushover_member(team, group, username, *, role="responder", delay_seconds=0):
    user = create_user(username, group)
    user.pushover_user_key = f"u-{username}"
    user.save()
    add_user_to_team(team, user, role=role)
    UserNotificationRule.create(user=user, method="pushover", delay_seconds=delay_seconds)
    return user


def team_policy_setup():
    group = create_group(slug=unique("infra"))
    team = create_team(group, slug="sre")
    policy = create_escalation_policy(team)
    return group, team, policy


def test_api_creates_team_rule_for_policy_team(client, admin_headers, db):
    _, team, policy = team_policy_setup()

    response = client.post(
        f"/api/escalation-policies/{policy.id}/rules",
        json={"position": 1, "delay_seconds": 1800, "target_type": "team", "target_id": team.id},
        headers=admin_headers,
    )

    assert response.status_code == 201
    rule = response.get_json()
    assert rule["target_type"] == "team"
    assert rule["target_id"] == team.id
    assert rule["target_name"] == team.name


def test_api_rejects_team_rule_for_another_team(client, admin_headers, db):
    group, _, policy = team_policy_setup()
    other_team = create_team(group, slug=unique("other"))

    response = client.post(
        f"/api/escalation-policies/{policy.id}/rules",
        json={"position": 1, "delay_seconds": 1800, "target_type": "team", "target_id": other_team.id},
        headers=admin_headers,
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "team_mismatch"


def test_api_switches_rule_to_team_without_target_id(client, admin_headers, db):
    group, team, policy = team_policy_setup()
    user = create_user("alice", group)
    add_user_to_team(team, user)
    rotation = create_rotation(team, users=[user])
    rule = create_escalation_policy_rule(policy, target_type="rotation", rotation=rotation)

    response = client.put(
        f"/api/escalation-policies/rules/{rule.id}",
        json={"target_type": "team", "target_id": team.id},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.get_json()["target_type"] == "team"
    assert response.get_json()["target_id"] == team.id


def test_team_rule_pages_every_responder_at_once(monkeypatch, db):
    group, team, policy = team_policy_setup()
    alice = pushover_member(team, group, "alice")
    bob = pushover_member(team, group, "bob", role="manager")
    pushover_member(team, group, "carol", role="viewer")
    create_escalation_policy_rule(policy, position=1, delay_seconds=1800, target_type="team")
    create_route(team, escalation_policy=policy)
    monkeypatch.setattr(notification_queue, "notify_alert", lambda *args, **kwargs: 1)
    sent = capture_pushover(monkeypatch)

    alert_group = upsert_alert(normalized_alert()).group

    assert alert_group.assignee is None
    assert alert_group.rotation is None
    assert sorted(rules.notification_recipient_ids(alert_group)) == sorted([alice.id, bob.id])
    assert rules.has_deliverable_user_notification(alert_group) is True

    assert rules.enqueue_user_notifications(alert_group) == 2
    assert sorted(sent) == ["u-alice", "u-bob"]


def test_each_member_keeps_their_own_rule_delay(monkeypatch, db):
    group, team, policy = team_policy_setup()
    pushover_member(team, group, "alice")
    bob = pushover_member(team, group, "bob", delay_seconds=600)
    create_escalation_policy_rule(policy, position=1, delay_seconds=1800, target_type="team")
    create_route(team, escalation_policy=policy)
    monkeypatch.setattr(notification_queue, "notify_alert", lambda *args, **kwargs: 1)
    sent = capture_pushover(monkeypatch)

    alert_group = upsert_alert(normalized_alert()).group

    assert rules.enqueue_user_notifications(alert_group) == 1
    assert sent == ["u-alice"]
    pending = UserNotificationDelivery.get(
        (UserNotificationDelivery.group == alert_group.id) & (UserNotificationDelivery.user == bob.id)
    )
    assert pending.status == "pending"


def test_acknowledge_stops_pending_pages_for_everyone(monkeypatch, db):
    group, team, policy = team_policy_setup()
    alice = pushover_member(team, group, "alice", delay_seconds=600)
    pushover_member(team, group, "bob", delay_seconds=600)
    create_escalation_policy_rule(policy, position=1, delay_seconds=1800, target_type="team")
    create_route(team, escalation_policy=policy)
    monkeypatch.setattr(notification_queue, "notify_alert", lambda *args, **kwargs: 1)
    monkeypatch.setattr("app.services.alerts.actions.notify_source_of_acknowledgement", lambda *args: None)
    monkeypatch.setattr("app.services.alerts.actions.update_alert_messages", lambda *args, **kwargs: None)
    capture_pushover(monkeypatch)

    alert_group = upsert_alert(normalized_alert()).group
    rules.enqueue_user_notifications(alert_group)

    acknowledge_alert(alert_group.id, user_id=alice.id)

    statuses = [
        delivery.status
        for delivery in UserNotificationDelivery.select().where(UserNotificationDelivery.group == alert_group.id)
    ]
    assert statuses == ["skipped", "skipped"]


def test_assigning_someone_narrows_pages_to_that_person(monkeypatch, db):
    group, team, policy = team_policy_setup()
    alice = pushover_member(team, group, "alice")
    pushover_member(team, group, "bob")
    create_escalation_policy_rule(policy, position=1, delay_seconds=1800, target_type="team")
    create_route(team, escalation_policy=policy)
    monkeypatch.setattr(notification_queue, "notify_alert", lambda *args, **kwargs: 1)
    sent = capture_pushover(monkeypatch)

    alert_group = upsert_alert(normalized_alert()).group
    alert_group.assignee = alice.id
    alert_group.save()
    alert_group = AlertGroup.get_by_id(alert_group.id)

    assert rules.notification_recipient_ids(alert_group) == [alice.id]
    assert rules.enqueue_user_notifications(alert_group) == 1
    assert sent == ["u-alice"]


def test_escalation_from_rotation_to_team_pages_everyone(monkeypatch, db):
    group, team, policy = team_policy_setup()
    alice = pushover_member(team, group, "alice")
    bob = pushover_member(team, group, "bob")
    rotation = create_rotation(team, name="Primary", users=[alice])
    create_escalation_policy_rule(policy, position=1, delay_seconds=1800, target_type="rotation", rotation=rotation)
    team_rule = create_escalation_policy_rule(policy, position=2, delay_seconds=1800, target_type="team")
    create_route(team, escalation_policy=policy)
    monkeypatch.setattr(notification_queue, "notify_alert", lambda *args, **kwargs: 1)
    monkeypatch.setattr(alert_escalation, "notify_alert", lambda *args, **kwargs: 1)
    sent = capture_pushover(monkeypatch)

    alert_group = upsert_alert(normalized_alert()).group
    assert alert_group.assignee.id == alice.id
    assert rules.notification_recipient_ids(alert_group) == [alice.id]

    alert_group.next_escalation_at = utc_now() - timedelta(seconds=1)
    alert_group.save()
    assert maybe_escalate_alert(alert_group) is True

    alert_group = AlertGroup.get_by_id(alert_group.id)
    assert alert_group.escalation_rule.id == team_rule.id
    assert alert_group.assignee is None
    assert alert_group.rotation is None
    assert sorted(rules.notification_recipient_ids(alert_group)) == sorted([alice.id, bob.id])
    assert AlertEvent.select().where(
        (AlertEvent.group == alert_group.id)
        & (AlertEvent.event_type == "escalated")
        & (AlertEvent.message == f"Escalated by policy rule #2 to team {team.name}")
    ).exists()

    assert rules.enqueue_user_notifications(alert_group, event_type="escalation") == 2
    assert sorted(sent) == ["u-alice", "u-bob"]


def test_disabled_team_rule_pages_nobody(db):
    group, team, policy = team_policy_setup()
    pushover_member(team, group, "alice")
    rule = create_escalation_policy_rule(policy, position=1, target_type="team", enabled=False)

    assert rules.notification_recipient_ids(
        AlertGroup(escalation_rule=rule, assignee=None)
    ) == []


def test_direct_email_and_voice_go_to_the_rule_user_not_the_assignee(db):
    group, team, _ = team_policy_setup()
    alice = create_user("alice", group)
    alice.phone = "+3200000001"
    alice.save()
    bob = create_user("bob", group)
    add_user_to_team(team, alice)
    add_user_to_team(team, bob)

    for method, key, expected in (
        ("email", "recipient_email", "alice@example.com"),
        ("voice_call", "recipient_phone", "+3200000001"),
    ):
        delivery = UserNotificationDelivery(user=alice, method=method, event_type="notification")
        assert rules.build_direct_channel_config(delivery)[key] == expected
