from urllib.parse import parse_qs

import pytest

from app.modules.common import utc_now
from app.modules.db import notifications_repo
from app.modules.db.models import AlertEvent, AlertGroup, UserNotificationDelivery
from app.notifiers.pushover.emergency import cancel_emergency_pages, emergency_tag
from app.notifiers.pushover.notifier import PushoverNotifier
from app.services.alerts.actions import acknowledge_alert, resolve_alert
from app.services.alerts.lifecycle import upsert_alert
from app.services.alerts.snooze import snooze_alert
from app.settings import Config
from tests.factories import (
    create_channel,
    create_group,
    create_impact_alert_group,
    create_route,
    create_service,
    create_team,
    create_user,
)


class FakeResponse:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self._body


@pytest.fixture
def cancel_calls(monkeypatch):
    calls = []

    def fake_request(method, url, *, data, headers, timeout):
        calls.append({
            "method": method,
            "url": url,
            "token": parse_qs(data)["token"][0],
            "content_type": headers["Content-Type"],
        })
        return FakeResponse({"status": 1, "canceled": 1, "request": "req"})

    monkeypatch.setattr("app.notifiers.pushover.emergency.safe_request", fake_request)
    monkeypatch.setattr(Config, "PUSHOVER_APP_TOKEN", "global-app-token")
    return calls


def _firing_group(severity="critical"):
    group = create_group(slug="infra")
    team = create_team(group, slug="sre")
    route = create_route(team)
    alert_group = create_impact_alert_group(
        team=team,
        service=create_service(team),
        route=route,
        severity=severity,
    )
    return group, team, alert_group


def _personal_delivery(group, alert_group, *, receipt="rEMERGENCY", username=None):
    user = create_user(username=username, group=group)
    user.pushover_user_key = "u" + user.username.upper()
    user.save()

    payload = {"pushover_request_id": "req"}
    if receipt:
        payload["pushover_receipt"] = receipt

    return UserNotificationDelivery.create(
        group=alert_group.id,
        user=user.id,
        method="pushover",
        event_type="notification",
        status="sent",
        scheduled_at=utc_now(),
        sent_at=utc_now(),
        provider="pushover",
        provider_payload=payload,
    )


def _events(alert_group, event_type):
    return list(
        AlertEvent.select().where(
            (AlertEvent.group == alert_group.id)
            & (AlertEvent.event_type == event_type)
        )
    )


def test_emergency_send_is_tagged_with_its_alert_and_keeps_the_receipt(monkeypatch, db):
    group, team, alert_group = _firing_group()
    channel = create_channel(
        group,
        team,
        channel_type="pushover",
        config={"app_token": "apptok", "target": "uTARGET"},
    )
    captured = {}

    def fake_request(method, url, *, json, timeout):
        captured["json"] = json
        return FakeResponse({"status": 1, "request": "req", "receipt": "rABC"})

    monkeypatch.setattr("app.notifiers.pushover.notifier.safe_request", fake_request)

    result = PushoverNotifier().send(channel, alert_group, "text")

    assert captured["json"]["priority"] == 2
    assert captured["json"]["tags"] == emergency_tag(alert_group.id)
    assert result["provider_payload"]["pushover_receipt"] == "rABC"


def test_non_emergency_send_has_no_tag_and_no_receipt(monkeypatch, db):
    group, team, alert_group = _firing_group(severity="high")
    channel = create_channel(
        group,
        team,
        channel_type="pushover",
        config={"app_token": "apptok", "target": "uTARGET"},
    )
    captured = {}

    def fake_request(method, url, *, json, timeout):
        captured["json"] = json
        return FakeResponse({"status": 1, "request": "req"})

    monkeypatch.setattr("app.notifiers.pushover.notifier.safe_request", fake_request)

    result = PushoverNotifier().send(channel, alert_group, "text")

    assert captured["json"]["priority"] == 1
    assert "tags" not in captured["json"]
    assert "pushover_receipt" not in result["provider_payload"]


def test_acknowledge_stops_the_other_responders_emergency_pages(cancel_calls, db):
    group, _team, alert_group = _firing_group()
    acker = _personal_delivery(group, alert_group, username="acker")
    _personal_delivery(group, alert_group, username="other")

    acknowledge_alert(alert_group.id, user_id=acker.user_id)

    assert cancel_calls == [{
        "method": "POST",
        "url": (
            "https://api.pushover.net/1/receipts/cancel_by_tag/"
            f"beacon-alert-{alert_group.id}.json"
        ),
        "token": "global-app-token",
        "content_type": "application/x-www-form-urlencoded",
    }]
    assert len(_events(alert_group, "pushover_emergency_cancelled")) == 1


def test_resolve_after_acknowledge_does_not_cancel_twice(cancel_calls, db):
    group, _team, alert_group = _firing_group()
    _personal_delivery(group, alert_group)

    acknowledge_alert(alert_group.id)
    resolve_alert(alert_group.id)

    assert len(cancel_calls) == 1


def test_manual_resolve_stops_emergency_pages(cancel_calls, db):
    group, _team, alert_group = _firing_group()
    _personal_delivery(group, alert_group)

    resolve_alert(alert_group.id)

    assert len(cancel_calls) == 1


def test_snooze_stops_emergency_pages(cancel_calls, db):
    group, _team, alert_group = _firing_group()
    _personal_delivery(group, alert_group)

    snooze_alert(alert_group.id, minutes=30)

    assert len(cancel_calls) == 1


def test_no_call_when_nothing_was_sent_as_an_emergency(cancel_calls, db):
    group, _team, alert_group = _firing_group(severity="high")
    _personal_delivery(group, alert_group, receipt=None)

    acknowledge_alert(alert_group.id)

    assert cancel_calls == []
    assert _events(alert_group, "pushover_emergency_cancelled") == []


def test_channel_pages_are_cancelled_with_the_channels_own_token(cancel_calls, db):
    group, team, alert_group = _firing_group()
    _personal_delivery(group, alert_group)
    channel = create_channel(
        group,
        team,
        channel_type="pushover",
        config={"app_token": "channel-app-token", "target": "gGROUP"},
    )
    same_token_channel = create_channel(
        group,
        team,
        channel_type="pushover",
        config={"target": "gOTHER"},
    )
    webhook = create_channel(group, team, channel_type="webhook")
    for each in (channel, same_token_channel, webhook):
        notifications_repo.save_notification(
            group_id=alert_group.id,
            channel_id=each.id,
            provider=each.channel_type,
            event_type="notification",
        )

    resolve_alert(alert_group.id)

    # The app-wide token once (personal rule plus the channel without a
    # token of its own), the channel's own token once, nothing for the webhook.
    assert sorted(call["token"] for call in cancel_calls) == [
        "channel-app-token",
        "global-app-token",
    ]


def test_a_failed_cancel_is_recorded_and_the_acknowledge_still_holds(monkeypatch, db):
    group, _team, alert_group = _firing_group()
    _personal_delivery(group, alert_group)
    monkeypatch.setattr(Config, "PUSHOVER_APP_TOKEN", "global-app-token")

    def failing_request(*args, **kwargs):
        raise RuntimeError("outbound hostname resolution failed")

    monkeypatch.setattr("app.notifiers.pushover.emergency.safe_request", failing_request)

    acknowledge_alert(alert_group.id)

    assert AlertGroup.get_by_id(alert_group.id).status == "acknowledged"
    failed = _events(alert_group, "pushover_emergency_cancel_failed")
    assert len(failed) == 1
    assert "outbound hostname resolution failed" in failed[0].message


def test_a_refused_cancel_is_recorded(monkeypatch, db):
    group, _team, alert_group = _firing_group()
    monkeypatch.setattr(Config, "PUSHOVER_APP_TOKEN", "global-app-token")
    _personal_delivery(group, alert_group)

    monkeypatch.setattr(
        "app.notifiers.pushover.emergency.safe_request",
        lambda *args, **kwargs: FakeResponse({"status": 0, "errors": ["application token is invalid"]}),
    )

    assert cancel_emergency_pages(alert_group, "acknowledged") == 0
    failed = _events(alert_group, "pushover_emergency_cancel_failed")
    assert "application token is invalid" in failed[0].message


def test_recovery_from_the_source_stops_emergency_pages(cancel_calls, db):
    group = create_group(slug="infra")
    team = create_team(group, slug="sre")
    route = create_route(team, source="alertmanager")

    def payload(status):
        return {
            "source": "alertmanager",
            "forced_route_id": route.id,
            "external_id": "external-recovery-1",
            "dedup_key": "recovery-1",
            "title": "DiskFull",
            "message": "DiskFull on host1",
            "severity": "critical",
            "labels": {"alertname": "DiskFull", "instance": "host1", "severity": "critical"},
            "payload": {},
            "status": status,
        }

    fired = upsert_alert(payload("firing"))
    alert_group = AlertGroup.get_by_id(fired.group.id)
    _personal_delivery(group, alert_group)

    upsert_alert(payload("resolved"))

    assert AlertGroup.get_by_id(alert_group.id).status == "resolved"
    assert len(cancel_calls) == 1
    assert cancel_calls[0]["url"].endswith(f"beacon-alert-{alert_group.id}.json")
