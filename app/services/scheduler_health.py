"""Is the scheduler still sending pages?

Every page goes through the scheduler: the first notification of a new
alert (alert_group_notification_job, after the group wait), every delayed
rule and retry (user_notification_rules_job), every escalation step
(reminder_job) and every overdue heartbeat (heartbeat_overdue_job). The web
pod keeps accepting alerts when the scheduler is gone, so /readyz stays
green while nobody is paged.

Each of those jobs records when it last finished a pass without an error
(record_job_run), and pipeline_status() compares that with the job's own
interval. /healthz/pipeline serves the result, so a monitor outside Beacon
can tell "alerts come in and pages go out" apart from "the web answers".
"""

import socket

from peewee import IntegrityError

from app.modules.common import utc_now
from app.modules.db.models import SchedulerJobRun
from app.settings import Config


def _pipeline_jobs():
    """Return {job id: interval seconds} for the jobs that send pages."""
    jobs = {
        "alert_group_notification_job": int(
            getattr(Config, "ALERT_GROUP_NOTIFICATION_CHECK_INTERVAL_SECONDS", 10)
        ),
        "user_notification_rules_job": int(
            getattr(Config, "USER_NOTIFICATION_RULES_CHECK_INTERVAL_SECONDS", 30)
        ),
        "reminder_job": int(Config.REMINDER_INTERVAL_SECONDS),
    }

    if bool(getattr(Config, "HEARTBEATS_ENABLED", True)):
        jobs["heartbeat_overdue_job"] = int(
            getattr(Config, "HEARTBEAT_CHECK_INTERVAL_SECONDS", 30)
        )

    return jobs


def record_job_run(job, now=None):
    """Remember that `job` just finished a pass without an error."""
    now = now or utc_now()
    host = socket.gethostname()

    updated = (
        SchedulerJobRun
        .update(last_finished_at=now, host=host)
        .where(SchedulerJobRun.job == job)
        .execute()
    )

    if updated:
        return

    try:
        SchedulerJobRun.create(job=job, last_finished_at=now, host=host)
    except IntegrityError:
        # Another scheduler created the row in between; it is fresh either way.
        pass


def pipeline_status(now=None):
    """Return (healthy, jobs) for the jobs that send pages.

    A job is stale when its last finished pass is older than three of its
    intervals, or [scheduler] pipeline_min_stale_seconds, whichever is
    longer; one that never finished a pass is stale too.
    """
    now = now or utc_now()
    runs = {
        run.job: run
        for run in SchedulerJobRun.select().where(
            SchedulerJobRun.job.in_(list(_pipeline_jobs()))
        )
    }

    jobs = {}
    healthy = True

    for job, interval in _pipeline_jobs().items():
        stale_after = max(interval * 3, int(Config.SCHEDULER_PIPELINE_MIN_STALE_SECONDS))
        run = runs.get(job)

        if run is None:
            jobs[job] = {
                "status": "stale",
                "last_finished_at": None,
                "age_seconds": None,
                "stale_after_seconds": stale_after,
            }
            healthy = False
            continue

        age = max(int((now - run.last_finished_at).total_seconds()), 0)
        status = "ok" if age <= stale_after else "stale"
        healthy = healthy and status == "ok"

        jobs[job] = {
            "status": status,
            "last_finished_at": run.last_finished_at.isoformat() + "Z",
            "age_seconds": age,
            "stale_after_seconds": stale_after,
        }

    return healthy, jobs
