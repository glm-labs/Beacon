from app.modules.db.models import UserNotificationDelivery
from app.notifiers.pushover.actions import build_pushover_action_signature
from app.services.notifications.rules import NOTIFICATION_METHOD_PUSHOVER
from app.settings import Config
from tests.factories import (
    add_user_to_team,
    create_channel,
    create_group,
    create_impact_alert_group,
    create_route,
    create_service,
    create_team,
    create_user,
)


def test_callback_rejects_bad_signature(client, db):
    group = create_group(slug="infra")
    team = create_team(group, slug="sre")
    route = create_route(team)
    service = create_service(team)
    channel = create_channel(group, team, channel_type="pushover", config={"app_token": "x", "target": "y"})
    alert_group = create_impact_alert_group(team=team, service=service, route=route)

    response = client.post(
        f"/api/integrations/pushover/callback"
        f"?kind=channel&alert_id={alert_group.id}&target_id={channel.id}"
        f"&signature=not-the-real-signature",
        data={"acknowledged": "1", "acknowledged_by": "uSOMEONE"},
    )

    assert response.status_code == 403


def test_callback_rejects_unknown_channel(client, db):
    group = create_group(slug="infra")
    team = create_team(group, slug="sre")
    route = create_route(team)
    service = create_service(team)
    alert_group = create_impact_alert_group(team=team, service=service, route=route)
    signature = build_pushover_action_signature(Config.PUSHOVER_ACTION_SECRET, alert_group.id, 999999, "channel")

    response = client.post(
        f"/api/integrations/pushover/callback"
        f"?kind=channel&alert_id={alert_group.id}&target_id=999999&signature={signature}",
        data={"acknowledged": "1", "acknowledged_by": "uSOMEONE"},
    )

    assert response.status_code == 403


def test_callback_acknowledges_and_attributes_mapped_user(client, db):
    group = create_group(slug="infra")
    team = create_team(group, slug="sre")
    route = create_route(team)
    service = create_service(team)
    channel = create_channel(group, team, channel_type="pushover", config={"app_token": "x", "target": "gTARGET"})
    alert_group = create_impact_alert_group(team=team, service=service, route=route)

    responder = create_user(username="responder", group=group)
    responder.pushover_user_key = "uRESPONDER"
    responder.save()
    add_user_to_team(team, responder, role="manager")

    signature = build_pushover_action_signature(
        Config.PUSHOVER_ACTION_SECRET, alert_group.id, channel.id, "channel"
    )

    response = client.post(
        f"/api/integrations/pushover/callback"
        f"?kind=channel&alert_id={alert_group.id}&target_id={channel.id}&signature={signature}",
        data={"acknowledged": "1", "acknowledged_by": "uRESPONDER"},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "acknowledged"
    assert body["user_id"] == responder.id

    alert_group = alert_group.__class__.get_by_id(alert_group.id)
    assert alert_group.status == "acknowledged"
    assert alert_group.acknowledged_by_id == responder.id


def test_callback_acknowledges_anonymously_when_pushover_key_unmapped(client, db):
    group = create_group(slug="infra")
    team = create_team(group, slug="sre")
    route = create_route(team)
    service = create_service(team)
    channel = create_channel(group, team, channel_type="pushover", config={"app_token": "x", "target": "gGROUP"})
    alert_group = create_impact_alert_group(team=team, service=service, route=route)

    signature = build_pushover_action_signature(
        Config.PUSHOVER_ACTION_SECRET, alert_group.id, channel.id, "channel"
    )

    response = client.post(
        f"/api/integrations/pushover/callback"
        f"?kind=channel&alert_id={alert_group.id}&target_id={channel.id}&signature={signature}",
        data={"acknowledged": "1", "acknowledged_by": "some-unregistered-device"},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "acknowledged"
    assert body["user_id"] is None

    alert_group = alert_group.__class__.get_by_id(alert_group.id)
    assert alert_group.status == "acknowledged"
    assert alert_group.acknowledged_by_id is None


def test_callback_ignores_non_acknowledge_pings(client, db):
    group = create_group(slug="infra")
    team = create_team(group, slug="sre")
    route = create_route(team)
    service = create_service(team)
    channel = create_channel(group, team, channel_type="pushover", config={"app_token": "x", "target": "y"})
    alert_group = create_impact_alert_group(team=team, service=service, route=route)

    signature = build_pushover_action_signature(
        Config.PUSHOVER_ACTION_SECRET, alert_group.id, channel.id, "channel"
    )

    response = client.post(
        f"/api/integrations/pushover/callback"
        f"?kind=channel&alert_id={alert_group.id}&target_id={channel.id}&signature={signature}",
        data={},
    )

    assert response.status_code == 200
    assert response.get_json() == {"status": "ignored"}

    alert_group = alert_group.__class__.get_by_id(alert_group.id)
    assert alert_group.status == "firing"


def test_callback_personal_delivery_falls_back_to_delivery_user(client, db):
    group = create_group(slug="infra")
    team = create_team(group, slug="sre")
    route = create_route(team)
    service = create_service(team)
    alert_group = create_impact_alert_group(team=team, service=service, route=route)

    owner = create_user(username="owner", group=group)
    add_user_to_team(team, owner, role="manager")

    delivery = UserNotificationDelivery.create(
        group=alert_group.id,
        user=owner.id,
        method=NOTIFICATION_METHOD_PUSHOVER,
        event_type="notification",
        status="sent",
        scheduled_at=alert_group.first_seen_at,
    )

    signature = build_pushover_action_signature(
        Config.PUSHOVER_ACTION_SECRET, alert_group.id, delivery.id, "delivery"
    )

    response = client.post(
        f"/api/integrations/pushover/callback"
        f"?kind=delivery&alert_id={alert_group.id}&target_id={delivery.id}&signature={signature}",
        data={"acknowledged": "1", "acknowledged_by": "unmapped-personal-device"},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["user_id"] == owner.id


def test_callback_rejects_delivery_kind_signed_for_different_target_id(client, db):
    group = create_group(slug="infra")
    team = create_team(group, slug="sre")
    route = create_route(team)
    service = create_service(team)
    alert_group = create_impact_alert_group(team=team, service=service, route=route)

    owner = create_user(username="owner2", group=group)
    add_user_to_team(team, owner, role="manager")

    delivery = UserNotificationDelivery.create(
        group=alert_group.id,
        user=owner.id,
        method=NOTIFICATION_METHOD_PUSHOVER,
        event_type="notification",
        status="sent",
        scheduled_at=alert_group.first_seen_at,
    )

    # Signed for kind=channel at the same numeric id: must not verify as
    # kind=delivery. This is the exact collision _action_payload's `kind`
    # segment exists to prevent.
    signature = build_pushover_action_signature(
        Config.PUSHOVER_ACTION_SECRET, alert_group.id, delivery.id, "channel"
    )

    response = client.post(
        f"/api/integrations/pushover/callback"
        f"?kind=delivery&alert_id={alert_group.id}&target_id={delivery.id}&signature={signature}",
        data={"acknowledged": "1", "acknowledged_by": "x"},
    )

    assert response.status_code == 403
