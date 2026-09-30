"""Add per-provider claim names for user contact fields.

Lets an SSO provider fill a user's Telegram, Slack, Mattermost and Pushover
identifiers from claims, the same way phone_claim already fills the phone
number. All four are nullable: no claim name means the field is not read.
"""

from playhouse.migrate import migrate
from peewee import CharField

from app.db import init_database
from app.migrations.introspection import (
    get_columns as migration_get_columns,
)
from app.modules.db.migrator import get_migrator
from app.modules.db.models import SsoProvider
from app.modules.sso.contact_claims import CONTACT_CLAIM_SETTINGS


db = init_database()
migrator = get_migrator(db)


def existing_columns(table_name):
    return {column.name for column in migration_get_columns(db, table_name)}


def upgrade():
    """Add the nullable contact claim columns to SSO providers."""
    table = SsoProvider._meta.table_name
    present = existing_columns(table)

    for setting in CONTACT_CLAIM_SETTINGS:
        if setting not in present:
            migrate(migrator.add_column(table, setting, CharField(null=True)))


def downgrade():
    """Remove the contact claim columns from SSO providers."""
    table = SsoProvider._meta.table_name
    present = existing_columns(table)

    for setting in CONTACT_CLAIM_SETTINGS:
        if setting in present:
            migrate(migrator.drop_column(table, setting))
