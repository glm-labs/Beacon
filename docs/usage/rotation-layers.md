---
title: Rotation Layers
description: Layered on-call schedules, membership periods, restrictions and final schedule calculation
---

# Rotation Layers

Rotation layers allow one rotation to contain several schedule rules.

Use layers when one duty line needs different coverage windows, for example:

- business hours;
- nights;
- weekends;
- primary and secondary duties;
- regional schedules with different timezones.

## Basic model

```text
Rotation

Layer: Business hours
Members:
  Ivan   position 0
  Petr   position 1
  Anna   position 2
Restrictions:
  Monday-Friday 09:00-18:00

Layer: Nights
Members:
  Petr   position 0
  Anna   position 1
  Ivan   position 2
Restrictions:
  Monday-Friday 18:00-09:00

Layer: Weekend
Members:
  Anna   position 0
  Ivan   position 1
  Petr   position 2
Restrictions:
  Saturday-Sunday 00:00-00:00
```

The rotation produces one final on-call user for a given time.

## Layer fields

A layer has:

- name;
- priority;
- enabled flag;
- start date/time;
- rotation type: daily, weekly or custom;
- handoff time;
- handoff weekday for weekly rotations;
- timezone;
- ordered member periods;
- optional restrictions.

## Member periods

Layer members are stored as membership periods.

A member period has:

- user;
- position;
- starts_at;
- ends_at;
- active flag.

```text
Ivan:
  position: 0
  starts_at: 2026-06-01 09:00
  ends_at:   2026-06-05 12:00

Ivan:
  position: 2
  starts_at: 2026-06-10 09:00
  ends_at:   null
```

This means Ivan participated in the layer during the first period, was absent between periods, and then joined again as a new period.

## Adding a layer member

When adding a user to a layer, you can set `starts_at`.

```json
{
  "user_id": 42,
  "position": 2,
  "starts_at": "2026-06-10T09:00:00"
}
```

If `starts_at` is omitted, Beacon uses the current time.

If `starts_at` does not include a timezone offset, Beacon treats it as local time in the layer timezone and stores it internally as UTC.

Example:

```text
Layer timezone: Europe/Moscow
starts_at from UI/API: 2026-06-10T09:00:00
stored UTC value:      2026-06-10T06:00:00
```

## Removing a layer member

Removing a layer member does not delete historical data.

Instead, Beacon closes the current membership period:

```text
active = false
ends_at = current time
```

Past shifts remain visible in the calendar.

Future shifts are calculated without this member.

## Re-adding a removed user

Re-adding the same user creates a new membership period.

Beacon does not reopen the old period and does not rewrite history.

```text
Old period:
  Ivan starts_at=2026-06-01 09:00
  Ivan ends_at=2026-06-05 12:00

New period:
  Ivan starts_at=2026-06-10 09:00
  Ivan ends_at=null
```

Calendar behavior:

```text
before 2026-06-05 12:00     Ivan may be shown
2026-06-05 to 2026-06-10    Ivan is not part of the layer
after 2026-06-10 09:00      Ivan may be shown again
```

## Member positions

Members rotate in position order.

```text
Position 0: Ivan
Position 1: Petr
Position 2: Anna
```

Changing a member position should not rewrite historical shifts.

For historical correctness, Beacon closes the old membership period and creates a new one with the new position.

## Restrictions

Restrictions define when a layer is active.

If a layer has no restrictions, it is active 24/7.

Examples:

```text
Monday-Friday 09:00-18:00
Monday-Friday 18:00-09:00
Saturday 00:00-00:00
Sunday 00:00-00:00
```

`00:00-00:00` means full day.

Restrictions are interpreted in the layer timezone.

## Priority

If multiple layers are active at the same time, the higher priority layer wins.

Example:

```text
Business hours: priority 10
Weekend:        priority 30
```

If both match, `Weekend` wins because it has higher priority.

## Overrides

Overrides always win over layer calculation.

Final order:

```text
override > highest-priority active layer > no assignment
```

## Timezone behavior

Use the layer timezone for recurring rules and member `starts_at` values from the UI.

Example:

```text
Timezone: Europe/Berlin
Restriction: Monday-Friday 09:00-18:00
Member starts_at: 2026-06-10 09:00
```

Both the restriction and the member start time mean local Berlin time.

UTC offsets may change because of daylight saving time.

## Best practices

- Use one rotation for one duty line.
- Use layers for different active windows inside the same duty line.
- Use separate rotations when you need separate calendars, for example primary and secondary.
- Keep priorities spaced, for example 10, 20, 30.
- Use `starts_at` when a user should join the schedule in the future.
- Remove members instead of deleting users if you want to preserve schedule history.
- Verify the final result in the calendar after changing members, restrictions, handoff time or timezone.
