"""Add snooze columns to alert groups.

A snoozed group stays firing but is held quiet until snoozed_until; see
app/services/alerts/snooze.py.
"""

from playhouse.migrate import migrate
from peewee import DateTimeField, IntegerField, TextField

from app.db import init_database
from app.migrations.introspection import (
    get_columns as migration_get_columns,
    get_indexes as migration_get_indexes,
)
from app.modules.db.migrator import get_migrator
from app.modules.db.models import AlertGroup


db = init_database()
migrator = get_migrator(db)

SNOOZED_UNTIL_INDEX = "alert_group_snoozed_until"


def _columns(table):
    return {column.name for column in migration_get_columns(db, table)}


def _indexes(table):
    return {index.name for index in migration_get_indexes(db, table)}


def upgrade():
    """Add snooze columns and the index the wake-up scan uses."""
    table = AlertGroup._meta.table_name
    present = _columns(table)
    operations = []

    if "snoozed_until" not in present:
        operations.append(
            migrator.add_column(table, "snoozed_until", DateTimeField(null=True))
        )
    if "snoozed_at" not in present:
        operations.append(
            migrator.add_column(table, "snoozed_at", DateTimeField(null=True))
        )
    if "snoozed_by_id" not in present:
        operations.append(
            # Plain nullable integer, like priority_set_by_id: adding a real
            # foreign key to an existing SQLite table needs a table rebuild.
            migrator.add_column(table, "snoozed_by_id", IntegerField(null=True))
        )
    if "snooze_reason" not in present:
        operations.append(
            migrator.add_column(table, "snooze_reason", TextField(null=True))
        )

    if operations:
        migrate(*operations)

    if SNOOZED_UNTIL_INDEX not in _indexes(table):
        migrate(migrator.add_index(table, ("snoozed_until",), False))


def downgrade():
    """Remove the snooze columns."""
    table = AlertGroup._meta.table_name

    if SNOOZED_UNTIL_INDEX in _indexes(table):
        migrate(migrator.drop_index(table, SNOOZED_UNTIL_INDEX))

    present = _columns(table)
    for column in ("snooze_reason", "snoozed_by_id", "snoozed_at", "snoozed_until"):
        if column in present:
            migrate(migrator.drop_column(table, column))
