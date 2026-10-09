"""A heartbeat that was off must not be overdue the moment it is switched on.

Regression: a heartbeat created disabled and enabled three days later
anchored its first deadline on created_at, was overdue on enable and paged
before its producer had run once.
"""

from datetime import timedelta

from app.modules.common import utc_now
from app.modules.db.models import Heartbeat
from app.services.heartbeats.service import pause_heartbeat, process_overdue_heartbeats, resume_heartbeat
from tests.factories import add_user_to_team, create_group, create_heartbeat, create_route, create_team, create_user


def _fixture():
    group = create_group()
    user = create_user(group=group)
    team = create_team(group)
    add_user_to_team(team, user)
    route = create_route(team, source="heartbeat")
    return team, route


def _age(heartbeat, days):
    """Pretend the heartbeat was created `days` ago and never pinged."""
    created = utc_now() - timedelta(days=days)
    Heartbeat.update(created_at=created, next_expected_at=created + timedelta(seconds=900)).where(
        Heartbeat.id == heartbeat.id
    ).execute()


def test_enabling_a_heartbeat_created_disabled_days_ago_does_not_page(client, db, admin_headers):
    team, route = _fixture()
    heartbeat = create_heartbeat(team, route, slug="pg-wal-archive", enabled=False,
                                 expected_interval_seconds=900, grace_period_seconds=900)
    _age(heartbeat, days=3)

    response = client.put(
        f"/api/heartbeats/{heartbeat.id}",
        headers=admin_headers,
        json={
            "team_id": team.id,
            "route_id": route.id,
            "name": heartbeat.name,
            "slug": heartbeat.slug,
            "mode": "interval",
            "expected_interval_seconds": 900,
            "grace_period_seconds": 900,
            "enabled": True,
        },
    )
    assert response.status_code == 200

    heartbeat = Heartbeat.get_by_id(heartbeat.id)
    assert heartbeat.next_expected_at > utc_now().replace(tzinfo=None) + timedelta(seconds=800)

    result = process_overdue_heartbeats(now=utc_now())
    assert result["overdue"] == 0
    assert Heartbeat.get_by_id(heartbeat.id).status != "overdue"


def test_resume_gives_the_producer_one_interval_from_now(db):
    team, route = _fixture()
    heartbeat = create_heartbeat(team, route, expected_interval_seconds=900, grace_period_seconds=900,
                                 last_seen_at=utc_now() - timedelta(hours=6))
    pause_heartbeat(heartbeat)

    resume_heartbeat(Heartbeat.get_by_id(heartbeat.id), now=utc_now())

    result = process_overdue_heartbeats(now=utc_now())
    assert result["overdue"] == 0
    assert Heartbeat.get_by_id(heartbeat.id).next_expected_at > utc_now().replace(tzinfo=None) + timedelta(seconds=800)


def test_an_enabled_heartbeat_that_stops_pinging_still_goes_overdue(db):
    """The fix only restarts the clock on enable and resume, not on every update."""
    team, route = _fixture()
    create_heartbeat(team, route, expected_interval_seconds=60, grace_period_seconds=60,
                     last_seen_at=utc_now() - timedelta(minutes=10),
                     next_expected_at=utc_now() - timedelta(minutes=9))

    result = process_overdue_heartbeats(now=utc_now())
    assert result["overdue"] == 1
