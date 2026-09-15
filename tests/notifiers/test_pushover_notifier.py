import pytest

from app.notifiers.pushover.actions import (
    build_pushover_action_signature,
    verify_pushover_action_signature,
)
from app.notifiers.pushover.notifier import PushoverNotifier
from app.settings import Config
from tests.factories import create_alert, create_channel, create_group, create_route, create_team


class FakeResponse:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self._body


def _pushover_channel(group, team, **config_overrides):
    config = {"app_token": "apptok", "target": "gTARGET"}
    config.update(config_overrides)
    return create_channel(group, team, channel_type="pushover", config=config)


def test_pushover_requires_app_token(db):
    group = create_group(slug="infra")
    team = create_team(group, slug="sre")
    route = create_route(team)
    channel = create_channel(group, team, channel_type="pushover", config={"target": "gTARGET"})
    alert = create_alert(route)

    monkeypatch_config = Config.PUSHOVER_APP_TOKEN
    Config.PUSHOVER_APP_TOKEN = ""
    try:
        with pytest.raises(RuntimeError, match="app_token is missing"):
            PushoverNotifier().send(channel, alert, "text")
    finally:
        Config.PUSHOVER_APP_TOKEN = monkeypatch_config


def test_pushover_requires_target(db):
    group = create_group(slug="infra")
    team = create_team(group, slug="sre")
    route = create_route(team)
    channel = create_channel(group, team, channel_type="pushover", config={"app_token": "apptok"})
    alert = create_alert(route)

    with pytest.raises(RuntimeError, match="target is missing"):
        PushoverNotifier().send(channel, alert, "text")


def test_pushover_critical_severity_sends_emergency_priority_with_callback(monkeypatch, db):
    group = create_group(slug="infra")
    team = create_team(group, slug="sre")
    route = create_route(team)
    channel = _pushover_channel(group, team)
    alert = create_alert(route)
    alert.severity = "critical"
    captured = {}

    def fake_request(method, url, *, json, timeout):
        captured["method"] = method
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse({"status": 1, "request": "abc123"})

    monkeypatch.setattr("app.notifiers.pushover.notifier.safe_request", fake_request)

    result = PushoverNotifier().send(channel, alert, "plain text", event_type="notification")

    assert result["provider"] == "pushover"
    assert result["provider_payload"]["pushover_request_id"] == "abc123"
    payload = captured["json"]
    assert payload["token"] == "apptok"
    assert payload["user"] == "gTARGET"
    assert payload["priority"] == 2
    assert payload["retry"] == 60
    assert payload["expire"] == 3600
    assert f"alert_id={alert.id}" in payload["callback"]
    assert f"target_id={channel.id}" in payload["callback"]
    assert "kind=channel" in payload["callback"]

    # The callback URL must actually verify against what the notifier signed.
    query = dict(pair.split("=") for pair in payload["callback"].split("?", 1)[1].split("&"))
    assert verify_pushover_action_signature(
        Config.PUSHOVER_ACTION_SECRET,
        query["signature"],
        alert.id,
        channel.id,
        "channel",
    )


def test_pushover_low_severity_has_no_retry_or_callback(monkeypatch, db):
    group = create_group(slug="infra")
    team = create_team(group, slug="sre")
    route = create_route(team)
    channel = _pushover_channel(group, team)
    alert = create_alert(route)
    alert.severity = "info"
    captured = {}

    def fake_request(method, url, *, json, timeout):
        captured["json"] = json
        return FakeResponse({"status": 1, "request": "abc"})

    monkeypatch.setattr("app.notifiers.pushover.notifier.safe_request", fake_request)

    PushoverNotifier().send(channel, alert, "plain text")

    assert captured["json"]["priority"] == -1
    assert "retry" not in captured["json"]
    assert "callback" not in captured["json"]


def test_pushover_acknowledged_event_never_reescalates_to_emergency(monkeypatch, db):
    group = create_group(slug="infra")
    team = create_team(group, slug="sre")
    route = create_route(team)
    channel = _pushover_channel(group, team)
    alert = create_alert(route)
    alert.severity = "critical"
    captured = {}

    def fake_request(method, url, *, json, timeout):
        captured["json"] = json
        return FakeResponse({"status": 1, "request": "abc"})

    monkeypatch.setattr("app.notifiers.pushover.notifier.safe_request", fake_request)

    PushoverNotifier().send(channel, alert, "plain text", event_type="acknowledged")

    assert captured["json"]["priority"] == -1
    assert "callback" not in captured["json"]


def test_pushover_rejects_error_response(monkeypatch, db):
    group = create_group(slug="infra")
    team = create_team(group, slug="sre")
    route = create_route(team)
    channel = _pushover_channel(group, team)
    alert = create_alert(route)

    def fake_request(method, url, *, json, timeout):
        return FakeResponse({"status": 0, "errors": ["invalid token"]})

    monkeypatch.setattr("app.notifiers.pushover.notifier.safe_request", fake_request)

    with pytest.raises(RuntimeError, match="invalid token"):
        PushoverNotifier().send(channel, alert, "text")


def test_pushover_no_callback_without_action_secret(monkeypatch, db):
    group = create_group(slug="infra")
    team = create_team(group, slug="sre")
    route = create_route(team)
    channel = _pushover_channel(group, team)
    alert = create_alert(route)
    alert.severity = "critical"
    captured = {}

    def fake_request(method, url, *, json, timeout):
        captured["json"] = json
        return FakeResponse({"status": 1, "request": "abc"})

    monkeypatch.setattr("app.notifiers.pushover.notifier.safe_request", fake_request)
    monkeypatch.setattr(Config, "PUSHOVER_ACTION_SECRET", "")

    PushoverNotifier().send(channel, alert, "plain text")

    assert "callback" not in captured["json"]


def test_pushover_custom_priority_map_overrides_default(monkeypatch, db):
    group = create_group(slug="infra")
    team = create_team(group, slug="sre")
    route = create_route(team)
    channel = _pushover_channel(group, team, priority_map={"warning": 2})
    alert = create_alert(route)
    alert.severity = "warning"
    captured = {}

    def fake_request(method, url, *, json, timeout):
        captured["json"] = json
        return FakeResponse({"status": 1, "request": "abc"})

    monkeypatch.setattr("app.notifiers.pushover.notifier.safe_request", fake_request)

    PushoverNotifier().send(channel, alert, "plain text")

    assert captured["json"]["priority"] == 2


def test_callback_target_kind_distinguishes_channel_from_delivery(db):
    group = create_group(slug="infra")
    team = create_team(group, slug="sre")
    channel = _pushover_channel(group, team)

    notifier = PushoverNotifier()
    assert notifier._callback_target_kind(channel) == "channel"

    from types import SimpleNamespace
    fake_delivery_channel = SimpleNamespace(id=channel.id, config={})
    assert notifier._callback_target_kind(fake_delivery_channel) == "delivery"


def test_action_signature_distinguishes_kind_at_same_id():
    secret = "shared-secret"
    channel_signature = build_pushover_action_signature(secret, 1, 5, "channel")
    delivery_signature = build_pushover_action_signature(secret, 1, 5, "delivery")

    assert channel_signature != delivery_signature
    assert not verify_pushover_action_signature(secret, channel_signature, 1, 5, "delivery")
    assert not verify_pushover_action_signature(secret, delivery_signature, 1, 5, "channel")
