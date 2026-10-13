from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.api.schemas.channels import ChannelCreateSchema
from app.notifiers.pushover.notifier import PushoverNotifier
from app.notifiers.pushover.sounds import normalize_sound_map
from app.settings import Config
from tests.factories import create_alert, create_channel, create_group, create_route, create_team


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"status": 1, "request": "abc"}


@pytest.fixture
def sent(monkeypatch):
    captured = []

    def fake_request(method, url, *, json, timeout):
        captured.append(json)
        return FakeResponse()

    monkeypatch.setattr("app.notifiers.pushover.notifier.safe_request", fake_request)
    return captured


def _alert_and_channel(severity, **config):
    group = create_group(slug="infra")
    team = create_team(group, slug="sre")
    route = create_route(team)
    channel = create_channel(
        group, team, channel_type="pushover",
        config={"app_token": "apptok", "target": "gTARGET", **config},
    )
    alert = create_alert(route)
    alert.severity = severity
    return alert, channel


def test_no_sound_without_configuration(monkeypatch, sent, db):
    monkeypatch.setattr(Config, "PUSHOVER_SOUNDS", {})
    alert, channel = _alert_and_channel("critical")

    PushoverNotifier().send(channel, alert, "text")

    assert "sound" not in sent[0]


def test_app_wide_sound_is_sent_for_its_severity(monkeypatch, sent, db):
    monkeypatch.setattr(Config, "PUSHOVER_SOUNDS", {"critical": "persistent", "high": "siren"})
    alert, channel = _alert_and_channel("critical")

    PushoverNotifier().send(channel, alert, "text")

    assert sent[0]["sound"] == "persistent"
    assert sent[0]["priority"] == 2


def test_unlisted_severity_keeps_the_device_default(monkeypatch, sent, db):
    monkeypatch.setattr(Config, "PUSHOVER_SOUNDS", {"critical": "persistent"})
    alert, channel = _alert_and_channel("warning")

    PushoverNotifier().send(channel, alert, "text")

    assert "sound" not in sent[0]


def test_channel_sound_map_overrides_app_wide_sound(monkeypatch, sent, db):
    monkeypatch.setattr(Config, "PUSHOVER_SOUNDS", {"critical": "persistent", "high": "siren"})
    alert, channel = _alert_and_channel("high", sound_map={"high": "echo"})

    PushoverNotifier().send(channel, alert, "text")

    assert sent[0]["sound"] == "echo"


def test_lifecycle_updates_carry_no_sound(monkeypatch, sent, db):
    monkeypatch.setattr(Config, "PUSHOVER_SOUNDS", {"critical": "persistent"})
    alert, channel = _alert_and_channel("critical")

    PushoverNotifier().send(channel, alert, "text", event_type="resolved")
    PushoverNotifier().send(channel, alert, "text", event_type="acknowledged")

    assert ["sound" in payload for payload in sent] == [False, False]


def test_personal_rule_delivery_uses_app_wide_sound(monkeypatch, sent, db):
    monkeypatch.setattr(Config, "PUSHOVER_SOUNDS", {"high": "siren"})
    monkeypatch.setattr(Config, "PUSHOVER_APP_TOKEN", "apptok")
    alert, _ = _alert_and_channel("high")
    personal = SimpleNamespace(id=7, name="Notification rule #1", channel_type="pushover", config={"target": "uPERSONAL"})

    PushoverNotifier().send(personal, alert, "text")

    assert sent[0]["user"] == "uPERSONAL"
    assert sent[0]["sound"] == "siren"


def test_invalid_app_wide_entries_are_ignored():
    assert normalize_sound_map({"Critical": " persistent ", "high": "bad sound!", "low": ""}) == {
        "critical": "persistent",
    }
    assert normalize_sound_map(["persistent"]) == {}


def test_channel_schema_validates_sound_map():
    schema = ChannelCreateSchema(
        name="Pushover", channel_type="pushover", enabled=True,
        config={"target": "gTARGET", "sound_map": {"Critical": "persistent"}},
    )
    assert schema.config["sound_map"] == {"critical": "persistent"}

    with pytest.raises(ValidationError, match="sound_map must be an object"):
        ChannelCreateSchema(name="Pushover", channel_type="pushover", enabled=True,
                            config={"target": "gTARGET", "sound_map": "persistent"})

    with pytest.raises(ValidationError, match="Pushover sound names"):
        ChannelCreateSchema(name="Pushover", channel_type="pushover", enabled=True,
                            config={"target": "gTARGET", "sound_map": {"critical": "rm -rf"}})
