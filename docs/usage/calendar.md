---
title: Calendar
description: On-call calendar view
---

# Calendar

Open:

```text
Calendar
```

The calendar shows on-call duty calculated from rotations, rotation layers, layer member periods, restrictions and overrides.

## Views

The first calendar view helps users understand the current schedule across visible teams.

Typical usage:

- see all available teams for the current week;
- open one team schedule;
- switch to month view for a specific team;
- verify rotation handoff times;
- verify layer restrictions;
- verify member start dates;
- verify overrides.

## What the calendar uses

The calendar takes into account:

- enabled rotations;
- enabled rotation layers;
- layer member periods;
- member order;
- member `starts_at`;
- member `ends_at`;
- rotation type;
- rotation interval and duration;
- handoff time;
- timezone;
- layer restrictions;
- overrides.

## Historical schedule behavior

Beacon keeps historical layer membership periods.

When a user is removed from a layer, the current membership period is closed with `ends_at`.

Past shifts are still shown.

Future shifts are calculated without that user.

When the same user is added again, Beacon creates a new membership period.

Example:

```text
2026-06-01 09:00  Ivan added
2026-06-05 12:00  Ivan removed
2026-06-10 09:00  Ivan added again
```

Calendar behavior:

```text
before 2026-06-05 12:00     Ivan may appear
2026-06-05 to 2026-06-10    Ivan does not appear
after 2026-06-10 09:00      Ivan may appear again
```

## Future member starts

A layer member can have `starts_at` in the future.

The member appears in the layer configuration immediately, but the calendar does not use that user until `starts_at`.

This is useful when a new engineer should join the rotation next week or after onboarding.

## Troubleshooting

If the calendar looks wrong, check:

1. The rotation is enabled.
2. The layer is enabled.
3. The layer has open member periods.
4. Member positions are correct.
5. Member `starts_at` is not in the future.
6. Member `ends_at` is not already reached.
7. Handoff time and timezone are correct.
8. Layer restrictions match the expected time window.
9. Overrides do not replace the expected user.
10. The user has access to the team through group and team membership.
