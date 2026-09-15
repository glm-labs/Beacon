from app.services.notifications.rules import (
    NOTIFICATION_METHOD_PUSHOVER,
    build_direct_channel_config,
    create_delivery,
    send_delivery,
)
from app.modules.common import utc_now
from app.settings import Config
from tests.factories import create_group, create_impact_alert_group, create_service, create_team, create_user


class FakeResponse:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self._body


def test_build_direct_channel_config_reads_users_own_pushover_key(db):
    group = create_group(slug="infra")
    team = create_team(group, slug="sre")
    user = create_user(username="oncall", group=group)
    user.pushover_user_key = "uPERSONAL"
    user.save()

    alert_group = create_impact_alert_group(team=team, service=create_service(team))
    delivery = create_delivery(
        group=alert_group,
        user=user,
        rule=None,
        method=NOTIFICATION_METHOD_PUSHOVER,
        event_type="notification",
        scheduled_at=utc_now(),
    )

    config = build_direct_channel_config(delivery)

    assert config["target"] == "uPERSONAL"


def test_personal_pushover_delivery_sends_with_delivery_kind_callback(monkeypatch, db):
    group = create_group(slug="infra")
    team = create_team(group, slug="sre")
    user = create_user(username="oncall2", group=group)
    user.pushover_user_key = "uPERSONAL2"
    user.save()

    alert_group = create_impact_alert_group(team=team, service=create_service(team), severity="critical")
    delivery = create_delivery(
        group=alert_group,
        user=user,
        rule=None,
        method=NOTIFICATION_METHOD_PUSHOVER,
        event_type="notification",
        scheduled_at=utc_now(),
    )

    captured = {}

    def fake_request(method, url, *, json, timeout):
        captured["json"] = json
        return FakeResponse({"status": 1, "request": "abc"})

    monkeypatch.setattr("app.notifiers.pushover.notifier.safe_request", fake_request)
    monkeypatch.setattr(Config, "PUSHOVER_APP_TOKEN", "global-app-token")

    sent = send_delivery(delivery)

    assert sent == 1
    payload = captured["json"]
    assert payload["token"] == "global-app-token"
    assert payload["user"] == "uPERSONAL2"
    assert f"kind=delivery&alert_id={alert_group.id}&target_id={delivery.id}" in payload["callback"]
