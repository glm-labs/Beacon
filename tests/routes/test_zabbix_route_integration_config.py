"""Regression coverage for the Zabbix route integration_config round trip.

Caught live (not by a unit test) while building acknowledge writeback:
the value was correctly validated (schema) and correctly persisted
(routes_view.build_route_integration_config), but the read-side serializer
(app/services/serializers/routes.py) had no "zabbix" branch, so
integration_config always came back as {} over the API even though the
database had the real value -- there are three separate per-source
touchpoints for route integration_config (schema validation, the
view-layer builder, and the serializer) and it's easy to update two of
three. These tests pin all three so a future source doesn't repeat it.
"""

from app.services.serializers.routes import serialize_route_integration_config
from app.views.routes_view import build_route_integration_config
from tests.factories import create_group, create_route, create_team


class FakeRoutePayload:
    def __init__(self, source, integration_config):
        self.source = source
        self.integration_config = integration_config


def test_build_route_integration_config_keeps_zabbix_fields():
    payload = FakeRoutePayload(
        "zabbix",
        {
            "zabbix": {
                "ack_writeback_enabled": True,
                "api_url": "http://zabbix.internal/",
                "api_token": "secret-token",
            }
        },
    )

    result = build_route_integration_config(payload)

    assert result == {
        "zabbix": {
            "ack_writeback_enabled": True,
            # trailing slash stripped, same normalization as api_url
            # elsewhere in the zabbix writeback (see
            # app/services/integrations/writebacks/zabbix.py)
            "api_url": "http://zabbix.internal",
            "api_token": "secret-token",
        }
    }


def test_build_route_integration_config_preserves_token_on_blank_update():
    current = FakeRoutePayload(
        "zabbix",
        {"zabbix": {"ack_writeback_enabled": True, "api_url": "http://a", "api_token": "old-token"}},
    )
    incoming = FakeRoutePayload(
        "zabbix",
        {"zabbix": {"ack_writeback_enabled": True, "api_url": "http://a"}},
    )

    result = build_route_integration_config(incoming, current_route=current)

    assert result["zabbix"]["api_token"] == "old-token"


def test_serialize_route_integration_config_exposes_zabbix_without_secret(db):
    group = create_group(slug="infra")
    team = create_team(group, slug="sre")
    route = create_route(
        team,
        source="zabbix",
        integration_config={
            "zabbix": {
                "ack_writeback_enabled": True,
                "api_url": "http://zabbix.internal",
                "api_token": "should-never-be-returned",
            }
        },
    )

    result = serialize_route_integration_config(route)

    assert result == {
        "zabbix": {
            "ack_writeback_enabled": True,
            "api_url": "http://zabbix.internal",
            "has_api_token": True,
        }
    }
    assert "should-never-be-returned" not in str(result)


def test_serialize_route_integration_config_zabbix_writeback_disabled_by_default(db):
    group = create_group(slug="infra")
    team = create_team(group, slug="sre")
    route = create_route(team, source="zabbix", integration_config={})

    result = serialize_route_integration_config(route)

    assert result == {
        "zabbix": {
            "ack_writeback_enabled": False,
            "api_url": None,
            "has_api_token": False,
        }
    }
