---
title: Teams, Rotations, Layers and Routes
description: How teams, layered rotations and alert routes work together
---

# Teams, Rotations, Layers and Routes

Beacon routes alerts through teams, rotations, layers and notification channels.

```text
Incoming alert
  -> Route
  -> Service
  -> Team
  -> Rotation / Escalation policy
  -> Final schedule
  -> On-call user
  -> Channels
```

## Team

A team is an on-call ownership unit inside a group.

Example:

```text
Group: Production
Team: Infrastructure
Team slug: infra
```

The team slug is commonly used in alert labels, for example with Alertmanager:

```yaml
team: infra
```

Teams define ownership and escalation behavior. Users must be active team members before they can be added to rotation layers.

## Service

A service is a logical affected system owned by a team.

Example:

```text
Team: Infrastructure
Service: RabbitMQ Cloud
Service slug: rabbitmq-cloud
Type: queue
Environment: production
Criticality: critical
```

Services help group alerts by the system that is broken, not only by the route that received the alert.

A service can have:

links to dashboards, logs, traces and repositories;
runbooks;
dependencies;
status and impact analytics;
optional default rotation or escalation policy.

## Rotation

A rotation is the route-facing schedule object. Routes point to rotations, and rotations produce the final on-call user.

A rotation belongs to one team and can contain one or more layers.

Example:

```text
Team: infra
Rotation: infra-primary
Timezone: Europe/Berlin
Reminder interval: 300 seconds
```

When a rotation is created, Beacon creates a default layer. If `Add all active team members to this rotation` is enabled, active team members are added to that default layer in order.

## Layer

A layer is a schedule rule inside a rotation.

Each layer has:

- name;
- priority;
- enabled flag;
- start time;
- rotation type;
- handoff time;
- optional weekly handoff day;
- timezone;
- ordered members;
- optional active time restrictions.

A rotation may have multiple layers. This is useful for different coverage patterns, for example:

```text
Layer: Business hours
Members: Ivan -> Petr -> Anna
Active: Monday-Friday 09:00-18:00

Layer: Nights
Members: Petr -> Anna -> Ivan
Active: Monday-Friday 18:00-09:00

Layer: Weekend
Members: Anna -> Ivan -> Petr
Active: Saturday-Sunday 00:00-00:00
```

## Layer priority

When more than one layer is active at the same time, the layer with the higher priority wins.

```text
priority 10: Business hours
priority 20: Nights
priority 30: Weekend
```

A higher priority layer overrides a lower priority layer for overlapping time windows.

## Layer restrictions

Restrictions define when a layer is active.

If a layer has no restrictions, it is active 24/7.

Restriction examples:

```text
Monday-Friday 09:00-18:00
Monday-Friday 18:00-09:00
Saturday-Sunday 00:00-00:00
```

`00:00-00:00` means the whole day.

Times are interpreted in the layer timezone. Store absolute timestamps in UTC, but define recurring weekly/daily restrictions in local layer time.

## Final schedule

The final schedule is the effective schedule used by the calendar and alert routing.

Order of precedence:

```text
rotation override > highest-priority active layer > no assignee
```

If no layer is active, Beacon returns no scheduled on-call user for that rotation. Routing and escalation logic can then decide how to handle the alert.

## Overrides

An override temporarily replaces the final scheduled user for a rotation.

Overrides apply on top of all layers.

Example:

```text
Rotation: infra-primary
Override: Anna replaces current on-call user
Window: 2026-05-25 12:00 -> 2026-05-26 12:00
```

## Route

A route can have a default service. This is useful when all alerts entering the route belong to the same logical system.

If one route receives alerts for multiple systems, configure service match rules. A service match rule can use alert labels, annotations or payload fields to attach the alert to the right service.

Example:

```text
Source: alertmanager
Team: infra
Rotation: infra-primary
Channels: infra-mattermost, infra-voice-critical
Matchers: {"labels": {"team": "infra"}}
```

A route may exist without a rotation. This can happen if a rotation is deleted. The route remains, but `rotation_id` is cleared. In that state, the route still exists as configuration, but it does not assign a scheduled on-call user from that rotation.

## Multiple routes for one team

One team can have multiple independent intake routes:

```text
infra-alertmanager -> source alertmanager -> Alertmanager token
infra-webhook      -> source webhook      -> Generic webhook token
infra-zabbix       -> source zabbix       -> Zabbix token
```

Routes can point to the same team, rotation and channels, or they can use different rotations and channels.

## Multiple rotations for one team

One team can have multiple rotations.

Example:

```text
Team: Cloud
Rotation: Cloud primary
Rotation: Cloud secondary
Rotation: Cloud weekend
```

In the calendar UI, a rotation is treated as a separate calendar. This prevents multiple rotations for the same team from being mixed into one schedule.
