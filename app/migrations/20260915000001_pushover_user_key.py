"""Add pushover_user_key so a user's own Pushover key can be mapped to them.

Same purpose as telegram_user_id/slack_user_id/mattermost_user_id: lets an
inbound callback attribute a Pushover acknowledge to a real user (see
app/views/integrations_view.py, pushover_callback()) and lets a personal
notification rule address that user's own Pushover key (see
app/services/notifications/rules.py, NOTIFICATION_METHOD_PUSHOVER).
"""

from playhouse.migrate import migrate
from peewee import CharField

from app.db import init_database
from app.migrations.introspection import (
    get_columns as migration_get_columns,
)
from app.modules.db.migrator import get_migrator
from app.modules.db.models import User


db = init_database()
migrator = get_migrator(db)


def table_has_column(table_name, column_name):
    return any(
        column.name == column_name
        for column in migration_get_columns(db, table_name)
    )


def upgrade():
    """Add nullable Pushover user key to users."""
    user_table = User._meta.table_name

    if not table_has_column(user_table, "pushover_user_key"):
        migrate(
            migrator.add_column(
                user_table,
                "pushover_user_key",
                CharField(null=True),
            )
        )


def downgrade():
    """Remove Pushover user key from users."""
    user_table = User._meta.table_name

    if table_has_column(user_table, "pushover_user_key"):
        migrate(
            migrator.drop_column(
                user_table,
                "pushover_user_key",
            )
        )
