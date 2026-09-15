---
title: Escalation Policies API
description: API reference for Beacon escalation policies and policy rules
---

# Escalation Policies API

Escalation policy endpoints require an authenticated user token.

```http
Authorization: Bearer USER_OR_API_TOKEN
```

Route intake tokens are only for incoming alert integrations and cannot be used to manage policies.

## List policies

```http
GET /api/escalation-policies
GET /api/escalation-policies?team_id=1
```

Response:

```json
[
  {
    "id": 1,
    "team_id": 1,
    "team_name": "Cloud OPS",
    "team_slug": "cloud",
    "group_id": 2,
    "group_slug": "infra",
    "name": "Critical escalation",
    "description": "Critical alerts chain",
    "enabled": true,
    "repeat_count": 1,
    "rules": [],
    "permissions": {
      "can_read": true,
      "can_write": true,
      "can_respond": true
    },
    "created_at": "2026-05-26T17:07:32.342717",
    "updated_at": "2026-05-26T17:07:32.342719"
  }
]
```

## Create policy

```http
POST /api/escalation-policies
```

Request:

```json
{
  "team_id": 1,
  "name": "Critical escalation",
  "description": "Critical alerts chain",
  "enabled": true,
  "repeat_count": 1
}
```

Response status:

```text
201 Created
```

## Get policy

```http
GET /api/escalation-policies/{policy_id}
```

Returns one policy with rules.

## Update policy

```http
PUT /api/escalation-policies/{policy_id}
```

Request:

```json
{
  "team_id": 1,
  "name": "Critical escalation",
  "description": "Critical alerts chain",
  "enabled": true,
  "repeat_count": 1
}
```

## Delete policy

```http
DELETE /api/escalation-policies/{policy_id}
```

Deletes or disables the policy depending on backend implementation. Existing alerts keep their stored policy state.

## Create rule

```http
POST /api/escalation-policies/{policy_id}/rules
```

Rotation target request:

```json
{
  "position": 1,
  "delay_seconds": 300,
  "target_type": "rotation",
  "target_id": 10,
  "enabled": true
}
```

User target request:

```json
{
  "position": 2,
  "delay_seconds": 600,
  "target_type": "user",
  "target_id": 42,
  "enabled": true
}
```

Rules are evaluated by `position` in ascending order.

## Update rule

```http
PUT /api/escalation-policies/rules/{rule_id}
```

Request:

```json
{
  "position": 2,
  "delay_seconds": 600,
  "target_type": "rotation",
  "target_id": 11,
  "enabled": true
}
```

## Delete rule

```http
DELETE /api/escalation-policies/rules/{rule_id}
```

## Route integration

Routes can use either a direct rotation or an escalation policy.

Simple rotation mode:

```json
{
  "team_id": 1,
  "name": "alertmanager-critical",
  "source": "alertmanager",
  "rotation_id": 10,
  "escalation_policy_id": null,
  "channel_ids": [3, 4],
  "matchers": {
    "labels": {
      "severity": "critical"
    }
  },
  "group_by": ["alertname", "instance"],
  "enabled": true
}
```

Escalation policy mode:

```json
{
  "team_id": 1,
  "name": "alertmanager-critical",
  "source": "alertmanager",
  "rotation_id": null,
  "escalation_policy_id": 1,
  "channel_ids": [3, 4],
  "matchers": {
    "labels": {
      "severity": "critical"
    }
  },
  "group_by": ["alertname", "instance"],
  "enabled": true
}
```

If `escalation_policy_id` is set, team reminder-based escalation settings are ignored for alerts created by that route.

## Alert fields

Alert responses include policy state when the alert was created through a policy route.

```json
{
  "id": 123,
  "status": "firing",
  "escalation_mode": "policy",
  "escalation_policy_id": 1,
  "escalation_policy_name": "Critical escalation",
  "escalation_rule_id": 5,
  "escalation_rule_position": 2,
  "escalation_rule_target_type": "rotation",
  "next_escalation_at": "2026-05-27T12:30:00",
  "last_escalated_at": "2026-05-27T12:20:00",
  "escalation_repeat_count": 0,
  "team_escalation_enabled": true,
  "team_escalation_after_reminders": 2
}
```

## Error responses

Common errors:

| HTTP status | Error | Meaning |
|---:|---|---|
| `400` | `rotation_team_mismatch` | Rule target rotation belongs to another team |
| `400` | `user_team_mismatch` | Rule target user is not a member of the policy team |
| `400` | `escalation_policy_team_mismatch` | Route uses a policy from another team |
| `403` | `permission_denied` | User does not have write permission |
| `404` | `not_found` | Policy, rule or target not found |
| `409` | `conflict` | Duplicate policy or rule position |
