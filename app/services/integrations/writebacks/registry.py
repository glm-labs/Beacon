"""Per-source "notify the origin system of an acknowledge" plugin point.

Mirrors app/services/integrations/normalizers/registry.py, but for the
opposite direction: normalizers turn an inbound alert source's payload
into a Beacon alert; a writeback turns a Beacon acknowledge back into a
call to that source's own API, so the source's own escalation/nagging
(Zabbix's, or anything added here later) stops believing nobody has
looked at it.

Adding a new source's writeback is one entry here plus one module next to
zabbix.py -- app/services/alerts/actions.py never needs to know a new
source exists.
"""

import logging

from app.services.integrations.writebacks import zabbix


logger = logging.getLogger("oncall.integrations")

WRITEBACKS = {
    "zabbix": zabbix.acknowledge_upstream,
}


def notify_source_of_acknowledgement(group, user):
    """Call the acknowledged group's source-writeback plugin, if any.

    Deliberately swallows every exception: this runs inside
    acknowledge_alert() after Beacon's own acknowledge has already
    committed, and a source system being unreachable must never make that
    look like the acknowledge itself failed.
    """
    writeback = WRITEBACKS.get(getattr(group, "source", None))
    if not writeback:
        return

    try:
        writeback(group, user)
    except Exception:  # noqa: BLE001 - see docstring
        logger.exception(
            "source acknowledge writeback failed",
            extra={
                "extra": {
                    "alert_group_id": group.id,
                    "source": group.source,
                }
            },
        )
