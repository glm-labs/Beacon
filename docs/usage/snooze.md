# Snoozing Alerts

Snooze holds a firing alert group quiet for a set time. Use it when you know
about a problem, cannot act on it yet, and do not want to be paged about it
again until a given moment: a vendor fix that lands at 14:00, a deploy that
will clear it, a disk that someone is already expanding.

## Snooze or acknowledge?

| | Acknowledge | Snooze |
|---|---|---|
| Status | `acknowledged` | stays `firing` |
| Ownership | someone owns it now | nobody has taken it yet |
| Notifications, reminders, escalation | stop | paused until the snooze ends |
| Ends | when the group is resolved or reopened | at the chosen time, or when ended by hand |

A snooze is a promise to look again later. When it ends the group pages as if
it had just started firing again, so it cannot quietly fall through the cracks.

## Snoozing a group

1. Open the alert group from the **Alerts** inbox.
2. In the footer, optionally type a reason, pick a duration (30 minutes to
   24 hours), and click **Snooze**.

The group shows a *Snoozed until …* badge in the inbox and in its details. The
reason, the user and the end time are recorded on the group's event timeline.

Snoozing a group that is already snoozed moves the end time; it does not add
to it. Only firing groups can be snoozed, and you need the same permission as
for acknowledging.

## While a group is snoozed

- No first notification, update, reminder or escalation is sent for it.
  Deliveries that were already queued are cancelled.
- New child alerts still join the group and are visible, but they do not page.
- The **Snoozed only** filter in the inbox lists running snoozes.

## When a snooze ends

A snooze ends when its time is up (checked on every reminder cycle), when
someone clicks **End snooze**, or when the group stops firing.

- If the group is still firing, it is notified again right away, its
  reminder count starts over, and an escalation policy restarts its delay from
  the current step.
- If it was acknowledged, resolved or merged in the meantime, the snooze is
  simply dropped. A group that fires again later starts loud.

## API

```http
POST /api/alerts/{id}/snooze
Content-Type: application/json

{"minutes": 240, "reason": "Vendor fix due at 14:00"}
```

`minutes` must be between 5 and 10080 (7 days). The UI offers up to 24 hours;
the API allows longer for planned work, though a maintenance window is
usually the better tool for that.

```http
DELETE /api/alerts/{id}/snooze
```

ends the snooze early. `GET /api/alerts?snoozed=1` lists groups with a running
snooze and `snoozed=0` hides them. Alert group responses carry `snoozed`,
`snoozed_until`, `snoozed_at`, `snoozed_by` and `snooze_reason`.
