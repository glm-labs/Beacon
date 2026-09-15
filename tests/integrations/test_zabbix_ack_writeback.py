from app.modules.db.models import Alert
from app.services.alerts.actions import acknowledge_alert
from app.services.integrations.writebacks import zabbix as zabbix_writeback
from app.services.integrations.writebacks.registry import notify_source_of_acknowledgement
from tests.factories import create_impact_alert_group, create_route, create_service, create_team, create_group


class FakeResponse:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self._body


def _zabbix_group(team, service, *, ack_writeback_enabled=True, api_url="http://zabbix.internal", api_token="tok", external_id="587557"):
    route = create_route(
        team,
        source="zabbix",
        integration_config={
            "zabbix": {
                "ack_writeback_enabled": ack_writeback_enabled,
                "api_url": api_url,
                "api_token": api_token,
            }
        },
    )
    group = create_impact_alert_group(team=team, service=service, route=route)
    group.source = "zabbix"
    group.save()

    if external_id:
        Alert.create(
            group=group,
            team=team,
            route=route,
            source="zabbix",
            external_id=external_id,
            dedup_key=f"zabbix-{external_id}",
            group_key=group.group_key,
            title=group.title,
            status="firing",
        )

    return group, route


def test_writeback_skips_when_source_has_no_plugin(db):
    # source defaults to "pytest" via create_impact_alert_group, which has
    # no registered writeback -- notify_source_of_acknowledgement must be
    # a silent no-op, not an error, for every other source.
    grp = create_group(slug="infra")
    team = create_team(grp, slug="sre")
    service = create_service(team)
    group = create_impact_alert_group(team=team, service=service)

    # Must not raise even though group.route is None and group.source
    # ("pytest") has no writeback registered.
    notify_source_of_acknowledgement(group, None)


def test_writeback_skips_when_disabled(monkeypatch, db):
    grp = create_group(slug="infra")
    team = create_team(grp, slug="sre")
    service = create_service(team)
    group, _route = _zabbix_group(team, service, ack_writeback_enabled=False)

    calls = []
    monkeypatch.setattr(
        "app.services.integrations.writebacks.zabbix.safe_request",
        lambda *a, **k: calls.append((a, k)) or FakeResponse({"result": True}),
    )

    notify_source_of_acknowledgement(group, None)

    assert calls == []


def test_writeback_calls_zabbix_event_acknowledge(monkeypatch, db):
    grp = create_group(slug="infra")
    team = create_team(grp, slug="sre")
    service = create_service(team)
    group, route = _zabbix_group(team, service, external_id="587557")
    captured = {}

    def fake_request(method, url, *, json, headers, timeout):
        captured["method"] = method
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return FakeResponse({"jsonrpc": "2.0", "result": {"eventids": ["587557"]}, "id": 1})

    monkeypatch.setattr("app.services.integrations.writebacks.zabbix.safe_request", fake_request)

    notify_source_of_acknowledgement(group, None)

    assert captured["method"] == "POST"
    assert captured["url"] == "http://zabbix.internal/api_jsonrpc.php"
    assert captured["json"]["method"] == "event.acknowledge"
    assert captured["json"]["params"]["eventids"] == ["587557"]
    assert captured["json"]["params"]["action"] == zabbix_writeback.ZABBIX_ACK_ACTION
    assert captured["json"]["auth"] == "tok"


def test_writeback_includes_user_display_name_in_message(monkeypatch, db):
    grp = create_group(slug="infra")
    team = create_team(grp, slug="sre")
    service = create_service(team)
    group, _route = _zabbix_group(team, service)
    captured = {}

    def fake_request(method, url, *, json, headers, timeout):
        captured["json"] = json
        return FakeResponse({"jsonrpc": "2.0", "result": {}, "id": 1})

    monkeypatch.setattr("app.services.integrations.writebacks.zabbix.safe_request", fake_request)

    from tests.factories import create_user
    user = create_user(username="on.call", group=grp)

    notify_source_of_acknowledgement(group, user)

    assert user.display_name in captured["json"]["params"]["message"]


def test_writeback_skips_without_zabbix_eventid(monkeypatch, db):
    grp = create_group(slug="infra")
    team = create_team(grp, slug="sre")
    service = create_service(team)
    group, _route = _zabbix_group(team, service, external_id=None)

    calls = []
    monkeypatch.setattr(
        "app.services.integrations.writebacks.zabbix.safe_request",
        lambda *a, **k: calls.append((a, k)) or FakeResponse({"result": True}),
    )

    notify_source_of_acknowledgement(group, None)

    assert calls == []


def test_writeback_swallows_zabbix_api_errors(monkeypatch, db):
    grp = create_group(slug="infra")
    team = create_team(grp, slug="sre")
    service = create_service(team)
    group, _route = _zabbix_group(team, service)

    def fake_request(method, url, *, json, headers, timeout):
        return FakeResponse({
            "jsonrpc": "2.0",
            "error": {"code": -32602, "message": "Invalid params.", "data": "No permissions"},
            "id": 1,
        })

    monkeypatch.setattr("app.services.integrations.writebacks.zabbix.safe_request", fake_request)

    # Must not raise -- a Zabbix-side rejection must never look like the
    # Beacon acknowledge itself failed.
    notify_source_of_acknowledgement(group, None)


def test_acknowledge_alert_end_to_end_triggers_zabbix_writeback(monkeypatch, db):
    grp = create_group(slug="infra")
    team = create_team(grp, slug="sre")
    service = create_service(team)
    group, _route = _zabbix_group(team, service, external_id="42")

    captured = {}

    def fake_request(method, url, *, json, headers, timeout):
        captured["json"] = json
        return FakeResponse({"jsonrpc": "2.0", "result": {}, "id": 1})

    monkeypatch.setattr("app.services.integrations.writebacks.zabbix.safe_request", fake_request)

    updated = acknowledge_alert(group.id, user_id=None)

    assert updated.status == "acknowledged"
    assert captured["json"]["params"]["eventids"] == ["42"]
