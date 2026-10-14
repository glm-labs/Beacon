"""Default notification rules from [notifications] default_rules."""

import pytest

import app.services.alerts.notification_queue as notification_queue
from app.api.schemas.notification_rules import NOTIFICATION_RULE_EVENT_TYPES
from app.modules.db.models import UserNotificationDelivery, UserNotificationRule
from app.services.alerts.lifecycle import upsert_alert
from app.services.notifications import rules
from app.services.notifications.default_rules import (
    ALLOWED_DEFAULT_RULE_EVENT_TYPES,
    ALLOWED_DEFAULT_RULE_METHODS,
    parse_default_notification_rules,
)
from app.services.oncall_health import check_team_oncall_health, check_team_paging_methods
from app.settings import Config, Settings
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


PUSHOVER_DEFAULTS = [
    {"method": "pushover", "delay_seconds": 0, "severities": ["critical", "high"]},
    {"method": "pushover", "delay_seconds": 600, "severities": ["medium", "warning"]},
]


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


def use_defaults(monkeypatch, raw):
    monkeypatch.setattr(Config, "NOTIFICATION_DEFAULT_RULES", parse_default_notification_rules(raw))


def team_member(team, group, username, *, pushover_key=True, role="responder"):
    user = create_user(username, group)
    if pushover_key:
        user.pushover_user_key = f"u-{username}"
        user.save()
    add_user_to_team(team, user, role=role)
    return user


def team_alert(monkeypatch):
    group = create_group(slug=unique("infra"))
    team = create_team(group, slug="sre")
    policy = create_escalation_policy(team)
    create_escalation_policy_rule(policy, position=1, delay_seconds=1800, target_type="team")
    create_route(team, escalation_policy=policy)
    monkeypatch.setattr(notification_queue, "notify_alert", lambda *args, **kwargs: 1)
    return group, team


def fire(severity="critical"):
    return upsert_alert({
        "source": "alertmanager",
        "team_slug": "sre",
        "external_id": unique("external"),
        "dedup_key": unique("dedup"),
        "title": "GPU fell off the bus",
        "message": "79",
        "severity": severity,
        "labels": {"alertname": "GpuXid", "severity": severity, "team": "sre"},
        "payload": {"source": "test"},
        "status": "firing",
    }).group


# -- parsing ---------------------------------------------------------------


def test_parse_accepts_rules_and_normalizes_severity_aliases():
    parsed = parse_default_notification_rules([
        {"method": "pushover", "severities": ["Disaster", "high", "critical"]},
        {"method": "email", "delay_seconds": 600, "event_types": ["escalation"]},
    ])

    assert [rule.to_dict() for rule in parsed] == [
        {"position": 1, "method": "pushover", "delay_seconds": 0, "severities": ["critical", "high"], "event_types": []},
        {"position": 2, "method": "email", "delay_seconds": 600, "severities": [], "event_types": ["escalation"]},
    ]


@pytest.mark.parametrize("raw", [None, "", []])
def test_parse_empty_setting_keeps_old_behaviour(raw):
    assert parse_default_notification_rules(raw) == []


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"method": "pushover"}, "must be a JSON list"),
        (["pushover"], "rule 1 must be a JSON object"),
        ([{"method": "sms"}], "rule 1: method must be one of"),
        ([{"method": "pushover", "delay_seconds": -1}], "delay_seconds"),
        ([{"method": "pushover", "delay_seconds": True}], "delay_seconds"),
        ([{"method": "pushover", "delay_seconds": "600"}], "delay_seconds"),
        ([{"method": "pushover", "severities": ["urgent"]}], "unknown severity 'urgent'"),
        ([{"method": "pushover", "severities": "critical"}], "severities must be a list"),
        ([{"method": "pushover", "event_types": ["paged"]}], "unknown event type(s) paged"),
        ([{"method": "pushover"}, {"method": "pushover", "delay": 60}], "rule 2: unknown field(s) delay"),
    ],
)
def test_parse_rejects_malformed_rules_loudly(raw, message):
    with pytest.raises(RuntimeError) as error:
        parse_default_notification_rules(raw)

    assert "[notifications] default_rules" in str(error.value)
    assert message in str(error.value)


def test_default_rule_vocabulary_matches_personal_rules():
    assert ALLOWED_DEFAULT_RULE_METHODS == rules.NOTIFICATION_RULE_METHODS
    assert ALLOWED_DEFAULT_RULE_EVENT_TYPES == NOTIFICATION_RULE_EVENT_TYPES


def test_setting_is_read_from_the_notifications_section(tmp_path):
    config = tmp_path / "beacon.conf"
    config.write_text(
        "[notifications]\n"
        "default_rules = [{\"method\": \"pushover\", \"severities\": [\"critical\"]}]\n",
        encoding="utf-8",
    )

    raw = Settings(str(config)).get_json("notifications", "default_rules", None)

    assert [rule.method for rule in parse_default_notification_rules(raw)] == ["pushover"]


# -- delivery ----------------------------------------------------------------


def test_member_without_rules_is_paged_by_the_default(monkeypatch, db):
    group, team = team_alert(monkeypatch)
    louis = team_member(team, group, "louis")
    use_defaults(monkeypatch, PUSHOVER_DEFAULTS)
    sent = capture_pushover(monkeypatch)

    alert_group = fire("critical")

    assert rules.has_deliverable_user_notification(alert_group) is True
    assert rules.enqueue_user_notifications(alert_group) == 1
    assert sent == ["u-louis"]
    delivery = UserNotificationDelivery.get(UserNotificationDelivery.user == louis.id)
    assert delivery.method == "pushover"
    assert delivery.rule_id is None
    assert delivery.status == "sent"


def test_own_rules_win_over_the_defaults(monkeypatch, db):
    group, team = team_alert(monkeypatch)
    gilles = team_member(team, group, "gilles")
    UserNotificationRule.create(user=gilles, method="pushover", delay_seconds=0, severities=["warning"])
    use_defaults(monkeypatch, PUSHOVER_DEFAULTS)
    sent = capture_pushover(monkeypatch)

    alert_group = fire("critical")

    assert rules.enqueue_user_notifications(alert_group) == 0
    assert sent == []


def test_delayed_default_waits_and_ack_cancellation_still_applies(monkeypatch, db):
    group, team = team_alert(monkeypatch)
    louis = team_member(team, group, "louis")
    use_defaults(monkeypatch, PUSHOVER_DEFAULTS)
    sent = capture_pushover(monkeypatch)

    alert_group = fire("warning")

    assert rules.enqueue_user_notifications(alert_group) == 0
    assert sent == []
    pending = UserNotificationDelivery.get(UserNotificationDelivery.user == louis.id)
    assert pending.status == "pending"
    assert (pending.scheduled_at - pending.created_at).total_seconds() >= 599

    rules.cancel_pending_group_deliveries(alert_group, event_types=["notification"], reason="acknowledged")
    assert UserNotificationDelivery.get_by_id(pending.id).status == "skipped"


def test_default_that_matches_no_severity_sends_nothing(monkeypatch, db):
    group, team = team_alert(monkeypatch)
    team_member(team, group, "louis")
    use_defaults(monkeypatch, [{"method": "pushover", "severities": ["critical"]}])
    sent = capture_pushover(monkeypatch)

    alert_group = fire("info")

    assert rules.has_deliverable_user_notification(alert_group) is False
    assert rules.enqueue_user_notifications(alert_group) == 0
    assert sent == []
    assert not UserNotificationDelivery.select().exists()


def test_unreachable_default_falls_back_to_browser_push(monkeypatch, db):
    group, team = team_alert(monkeypatch)
    louis = team_member(team, group, "louis", pushover_key=False)
    use_defaults(monkeypatch, PUSHOVER_DEFAULTS)
    sent = capture_pushover(monkeypatch)

    alert_group = fire("critical")
    rules.enqueue_user_notifications(alert_group)

    assert sent == []
    methods = [delivery.method for delivery in UserNotificationDelivery.select().where(UserNotificationDelivery.user == louis.id)]
    assert methods == ["browser_push"]


def test_pushover_default_needs_the_app_token(monkeypatch, db):
    group = create_group(slug=unique("infra"))
    user = create_user("louis", group)
    user.pushover_user_key = "u-louis"
    user.save()
    use_defaults(monkeypatch, PUSHOVER_DEFAULTS)

    monkeypatch.setattr(Config, "PUSHOVER_APP_TOKEN", "")
    assert rules.usable_default_rules(user) == []

    monkeypatch.setattr(Config, "PUSHOVER_APP_TOKEN", "app-token")
    assert [rule.delay_seconds for rule in rules.usable_default_rules(user)] == [0, 600]


def test_email_default_needs_smtp_and_an_address(monkeypatch, db):
    group = create_group(slug=unique("infra"))
    user = create_user("louis", group)
    use_defaults(monkeypatch, [{"method": "email"}])

    monkeypatch.setattr(Config, "SMTP_HOST", "")
    assert rules.usable_default_rules(user) == []

    monkeypatch.setattr(Config, "SMTP_HOST", "smtp.example.com")
    assert len(rules.usable_default_rules(user)) == 1

    user.email = None
    assert rules.usable_default_rules(user) == []


def test_without_defaults_nothing_changes(monkeypatch, db):
    group, team = team_alert(monkeypatch)
    louis = team_member(team, group, "louis")
    monkeypatch.setattr(Config, "NOTIFICATION_DEFAULT_RULES", [])
    sent = capture_pushover(monkeypatch)

    rules.enqueue_user_notifications(fire("critical"))

    assert sent == []
    methods = [delivery.method for delivery in UserNotificationDelivery.select().where(UserNotificationDelivery.user == louis.id)]
    assert methods == ["browser_push"]


# -- profile endpoint ------------------------------------------------------------


def test_defaults_endpoint_says_whether_they_apply(client, admin_user, admin_headers, monkeypatch):
    use_defaults(monkeypatch, PUSHOVER_DEFAULTS)
    monkeypatch.setattr(Config, "PUSHOVER_APP_TOKEN", "app-token")

    response = client.get("/api/profile/notification-rules/defaults", headers=admin_headers)

    assert response.status_code == 200
    body = response.get_json()
    assert body["configured"] is True
    assert body["has_custom_rules"] is False
    assert body["applies"] is False
    assert [rule["reaches_user"] for rule in body["rules"]] == [False, False]

    admin_user.pushover_user_key = "u-admin"
    admin_user.save()

    body = client.get("/api/profile/notification-rules/defaults", headers=admin_headers).get_json()
    assert body["applies"] is True
    assert body["rules"][0] == {
        "position": 1,
        "method": "pushover",
        "delay_seconds": 0,
        "severities": ["critical", "high"],
        "event_types": [],
        "reaches_user": True,
    }

    UserNotificationRule.create(user=admin_user, method="email")

    body = client.get("/api/profile/notification-rules/defaults", headers=admin_headers).get_json()
    assert body["has_custom_rules"] is True
    assert body["applies"] is False


def test_defaults_endpoint_without_configuration(client, admin_headers, monkeypatch):
    monkeypatch.setattr(Config, "NOTIFICATION_DEFAULT_RULES", [])

    body = client.get("/api/profile/notification-rules/defaults", headers=admin_headers).get_json()

    assert body == {"configured": False, "has_custom_rules": False, "applies": False, "rules": []}


# -- on-call health ------------------------------------------------------------


def paging_issue_users(team):
    return sorted(
        issue.username
        for issue in check_team_paging_methods(team, [])
        if issue.code == "user_has_no_paging_method"
    )


def test_health_flags_pageable_users_nothing_reaches(monkeypatch, db):
    group, team = team_alert(monkeypatch)
    monkeypatch.setattr(Config, "PUSHOVER_APP_TOKEN", "app-token")
    monkeypatch.setattr(Config, "NOTIFICATION_DEFAULT_RULES", [])
    gilles = team_member(team, group, "gilles", role="manager")
    UserNotificationRule.create(user=gilles, method="pushover")
    team_member(team, group, "louis")
    team_member(team, group, "viewer", role="viewer")

    assert paging_issue_users(team) == ["louis"]

    use_defaults(monkeypatch, PUSHOVER_DEFAULTS)
    assert paging_issue_users(team) == []


def test_health_flags_a_disabled_or_unreachable_own_rule(monkeypatch, db):
    group, team = team_alert(monkeypatch)
    monkeypatch.setattr(Config, "PUSHOVER_APP_TOKEN", "app-token")
    use_defaults(monkeypatch, PUSHOVER_DEFAULTS)
    louis = team_member(team, group, "louis", pushover_key=False)
    UserNotificationRule.create(user=louis, method="pushover")

    # An own rule switches the defaults off, and it cannot reach louis.
    assert paging_issue_users(team) == ["louis"]


def test_health_covers_rotation_and_user_targets(monkeypatch, db):
    group = create_group(slug=unique("infra"))
    team = create_team(group, slug=unique("dc"))
    monkeypatch.setattr(Config, "NOTIFICATION_DEFAULT_RULES", [])
    alice = team_member(team, group, "alice", role="viewer")
    bob = team_member(team, group, "bob", role="viewer")
    rotation = create_rotation(team, users=[alice])
    policy = create_escalation_policy(team)
    create_escalation_policy_rule(policy, position=1, target_type="rotation", rotation=rotation)
    create_escalation_policy_rule(policy, position=2, target_type="user", user=bob)

    assert paging_issue_users(team) == ["alice", "bob"]


def test_team_health_payload_includes_the_issue(monkeypatch, db):
    group, team = team_alert(monkeypatch)
    monkeypatch.setattr(Config, "NOTIFICATION_DEFAULT_RULES", [])
    team_member(team, group, "louis")

    payload = check_team_oncall_health(team, include_rotation_issues=False)

    issue = next(item for item in payload["issues"] if item["code"] == "user_has_no_paging_method")
    assert issue["username"] == "louis"
    assert issue["target_type"] == "user"
    assert "default_rules" in issue["hint"]
