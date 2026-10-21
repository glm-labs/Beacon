"""Record when each scheduler job last finished, for /healthz/pipeline."""

from app.db import init_database
from app.modules.db.models import SchedulerJobRun


db = init_database()


def upgrade() -> None:
    if not db.table_exists(SchedulerJobRun._meta.table_name):
        db.create_tables([SchedulerJobRun], safe=True)


def downgrade() -> None:
    if db.table_exists(SchedulerJobRun._meta.table_name):
        db.drop_tables([SchedulerJobRun], safe=True)
