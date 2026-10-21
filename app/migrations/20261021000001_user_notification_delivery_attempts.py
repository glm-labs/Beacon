"""Count the send attempts of a user notification delivery.

A failed personal delivery (a Pushover page that hit a DNS error, a
timeout, a 5xx) is tried again a few times before it is marked failed; see
app/services/notifications/rules.py, _retry_or_fail_delivery. The counter
is what bounds that.
"""

from playhouse.migrate import migrate
from peewee import IntegerField

from app.db import init_database
from app.migrations.introspection import (
    get_columns as migration_get_columns,
)
from app.modules.db.migrator import get_migrator
from app.modules.db.models import UserNotificationDelivery


db = init_database()
migrator = get_migrator(db)


def table_has_column(table_name, column_name):
    return any(
        column.name == column_name
        for column in migration_get_columns(db, table_name)
    )


def upgrade():
    """Add the attempt counter to user notification deliveries."""
    table = UserNotificationDelivery._meta.table_name

    if not table_has_column(table, "attempts"):
        migrate(
            migrator.add_column(
                table,
                "attempts",
                IntegerField(default=0),
            )
        )


def downgrade():
    """Remove the attempt counter from user notification deliveries."""
    table = UserNotificationDelivery._meta.table_name

    if table_has_column(table, "attempts"):
        migrate(
            migrator.drop_column(
                table,
                "attempts",
            )
        )
