import pytest
from pydantic import ValidationError

from app.api.schemas.channels import ChannelCreateSchema, ChannelUpdateSchema
from app.api.schemas.routes import RouteCreateSchema
from app.services.channel_config import CHANNEL_SECRET_PLACEHOLDER


def make_pushover_schema(config, schema=ChannelCreateSchema):
    return schema(
        name="On-call Pushover",
        channel_type="pushover",
        config=config,
        enabled=True,
    )


def test_pushover_requires_target():
    with pytest.raises(ValidationError, match="requires target"):
        make_pushover_schema({"app_token": "apptok"})


def test_pushover_app_token_is_optional():
    schema = make_pushover_schema({"target": "gTARGET"})
    assert schema.config["target"] == "gTARGET"
    assert "app_token" not in schema.config


def test_pushover_priority_map_must_be_object():
    with pytest.raises(ValidationError, match="priority_map must be an object"):
        make_pushover_schema({"target": "gTARGET", "priority_map": "not-a-dict"})


def test_pushover_priority_map_values_must_be_in_range():
    with pytest.raises(ValidationError, match="between -2 and 2"):
        make_pushover_schema({"target": "gTARGET", "priority_map": {"critical": 5}})


def test_pushover_priority_map_is_normalized_to_ints():
    schema = make_pushover_schema(
        {"target": "gTARGET", "priority_map": {"critical": "2", "info": -1}}
    )
    assert schema.config["priority_map"] == {"critical": 2, "info": -1}


def test_pushover_secret_placeholder_rejected_on_create():
    with pytest.raises(ValidationError, match="placeholders are only valid during updates"):
        make_pushover_schema(
            {"target": "gTARGET", "app_token": CHANNEL_SECRET_PLACEHOLDER}
        )


def test_pushover_secret_placeholder_allowed_on_update():
    schema = make_pushover_schema(
        {"target": "gTARGET", "app_token": CHANNEL_SECRET_PLACEHOLDER},
        schema=ChannelUpdateSchema,
    )
    assert schema.config["app_token"] == CHANNEL_SECRET_PLACEHOLDER


def make_zabbix_route_schema(integration_config, **overrides):
    payload = {
        "team_id": 1,
        "name": "Zabbix",
        "source": "zabbix",
        "integration_config": integration_config,
    }
    payload.update(overrides)
    return RouteCreateSchema(**payload)


def test_zabbix_writeback_disabled_by_default_needs_no_config():
    schema = make_zabbix_route_schema({})
    assert schema.integration_config == {}


def test_zabbix_writeback_enabled_requires_api_url():
    with pytest.raises(ValidationError, match="requires api_url"):
        make_zabbix_route_schema({"zabbix": {"ack_writeback_enabled": True}})


def test_zabbix_writeback_enabled_with_api_url_is_valid():
    schema = make_zabbix_route_schema(
        {
            "zabbix": {
                "ack_writeback_enabled": True,
                "api_url": "http://zabbix.internal",
            }
        }
    )
    assert schema.integration_config["zabbix"]["api_url"] == "http://zabbix.internal"
