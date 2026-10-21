import os
import time
from datetime import timedelta

import app.views.health_view as health_view
from app.modules.common import utc_now
from app.modules.db.models import SchedulerJobRun
from app.services import scheduler
from app.services.scheduler_health import pipeline_status, record_job_run


PAGING_JOBS = (
    "alert_group_notification_job",
    "user_notification_rules_job",
    "reminder_job",
    "heartbeat_overdue_job",
)


def _all_jobs_ran(now=None):
    for job in PAGING_JOBS:
        record_job_run(job, now=now)


def test_pipeline_is_ok_when_every_paging_job_ran_recently(client, db):
    _all_jobs_ran()

    response = client.get("/healthz/pipeline")

    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "ok"
    assert set(body["jobs"]) == set(PAGING_JOBS)
    assert all(job["status"] == "ok" for job in body["jobs"].values())


def test_pipeline_is_stale_when_a_paging_job_stopped(client, db):
    _all_jobs_ran()
    record_job_run("alert_group_notification_job", now=utc_now() - timedelta(minutes=10))

    response = client.get("/healthz/pipeline")

    assert response.status_code == 503
    body = response.get_json()
    assert body["status"] == "stale"
    stopped = body["jobs"]["alert_group_notification_job"]
    assert stopped["status"] == "stale"
    assert stopped["age_seconds"] >= 600
    assert stopped["stale_after_seconds"] == 120
    assert body["jobs"]["reminder_job"]["status"] == "ok"


def test_pipeline_is_stale_before_the_scheduler_ever_ran(client, db):
    response = client.get("/healthz/pipeline")

    assert response.status_code == 503
    body = response.get_json()
    assert body["status"] == "stale"
    assert body["jobs"]["reminder_job"]["last_finished_at"] is None


def test_stale_window_is_three_intervals_but_never_below_the_minimum(db, monkeypatch):
    monkeypatch.setattr(scheduler.Config, "REMINDER_INTERVAL_SECONDS", 300)
    now = utc_now()
    _all_jobs_ran(now=now)
    record_job_run("reminder_job", now=now - timedelta(seconds=800))

    healthy, jobs = pipeline_status(now=now)

    assert healthy is True
    assert jobs["reminder_job"]["stale_after_seconds"] == 900
    assert jobs["alert_group_notification_job"]["stale_after_seconds"] == 120


def test_heartbeat_job_is_left_out_when_heartbeats_are_off(db, monkeypatch):
    monkeypatch.setattr(scheduler.Config, "HEARTBEATS_ENABLED", False, raising=False)
    _all_jobs_ran()

    healthy, jobs = pipeline_status()

    assert healthy is True
    assert "heartbeat_overdue_job" not in jobs


def test_record_job_run_keeps_one_row_per_job(db):
    record_job_run("reminder_job", now=utc_now() - timedelta(minutes=5))
    record_job_run("reminder_job")

    rows = list(SchedulerJobRun.select().where(SchedulerJobRun.job == "reminder_job"))
    assert len(rows) == 1
    assert utc_now() - rows[0].last_finished_at < timedelta(seconds=5)


def test_pipeline_does_not_expose_database_errors(client, monkeypatch):
    def broken_status():
        raise RuntimeError("postgresql://beacon:super-secret@db.internal/beacon")

    monkeypatch.setattr(health_view, "pipeline_status", broken_status)

    response = client.get("/healthz/pipeline")

    assert response.status_code == 503
    assert response.get_json() == {
        "status": "error",
        "database": "error",
        "database_error": "database check failed",
    }
    assert "super-secret" not in response.get_data(as_text=True)


def test_pipeline_needs_no_login(client, db, monkeypatch):
    monkeypatch.setattr(scheduler.Config, "API_AUTH_REQUIRED", True)
    _all_jobs_ran()

    assert client.get("/healthz/pipeline").status_code == 200


def test_paging_jobs_record_a_finished_pass(db, monkeypatch):
    monkeypatch.setattr(scheduler, "send_unacked_reminders", lambda: 0)
    monkeypatch.setattr(scheduler, "process_due_user_notifications", lambda: 0)
    monkeypatch.setattr(
        scheduler,
        "process_due_alert_group_notifications",
        lambda limit: {"processed": 0, "sent": 0, "skipped": 0, "failed": 0},
    )
    monkeypatch.setattr(
        scheduler,
        "process_overdue_heartbeats",
        lambda limit: {"processed": 0, "overdue": 0, "unchanged": 0, "failed": 0},
    )

    scheduler.reminder_job()
    scheduler.user_notification_rules_job()
    scheduler.alert_group_notification_job()
    scheduler.heartbeat_overdue_job()

    db.connect(reuse_if_open=True)
    assert {run.job for run in SchedulerJobRun.select()} == set(PAGING_JOBS)


def test_a_job_that_fails_records_nothing(db, monkeypatch):
    def broken():
        raise RuntimeError("database is gone")

    monkeypatch.setattr(scheduler, "send_unacked_reminders", broken)

    scheduler.reminder_job()

    db.connect(reuse_if_open=True)
    assert SchedulerJobRun.select().count() == 0


def test_alive_job_touches_the_alive_file(tmp_path, monkeypatch):
    alive = tmp_path / "scheduler.alive"
    monkeypatch.setattr(scheduler.Config, "SCHEDULER_ALIVE_FILE", str(alive), raising=False)

    assert scheduler.scheduler_alive_job() is True
    first = alive.stat().st_mtime

    os.utime(alive, (first - 120, first - 120))
    assert scheduler.scheduler_alive_job() is True
    assert alive.stat().st_mtime > time.time() - 5


def test_alive_job_is_off_without_a_path(monkeypatch):
    monkeypatch.setattr(scheduler.Config, "SCHEDULER_ALIVE_FILE", "", raising=False)

    assert scheduler.scheduler_alive_job() is False


def test_alive_job_survives_an_unwritable_path(tmp_path, monkeypatch):
    monkeypatch.setattr(
        scheduler.Config,
        "SCHEDULER_ALIVE_FILE",
        str(tmp_path / "missing-dir" / "scheduler.alive"),
        raising=False,
    )

    assert scheduler.scheduler_alive_job() is False
