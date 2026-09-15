---
title: First Login and Setup
description: Initial setup in the Beacon web UI
---

# First Login and Setup

Open:

```text
/login
```

Log in with the administrator user created by `manage.py create-admin`.

## Step 1. Create a group

Open:

```text
Administration -> Groups
```

Create a group:

```text
Slug: production
Name: Production
```

## Step 2. Create users

Open:

```text
Administration -> Users
```

Create users:

```text
ivan
petr
sergey
```

### Alternative: sync admins from a Slack usergroup

Instead of creating users manually, you can import them from a Slack usergroup with the `sync-slack-admins` management command.

The command requires a bot token with the following scopes: `usergroups:read`, `users:read`, `users:read.email`.

Run once to provision all members of the group as admins:

```bash
python manage.py sync-slack-admins --usergroup admins
```

Or pass the token explicitly:

```bash
python manage.py sync-slack-admins \
  --slack-token xoxb-... \
  --usergroup admins
```

The `--usergroup` argument accepts a Slack usergroup handle (`admins`, `@admins`) or a raw group ID (`S0123ABCDE`).

For newly created users a random password is generated and printed in the JSON output. To set a fixed password instead:

```bash
python manage.py sync-slack-admins --usergroup admins --password changeme
```

For each member the command:

- creates the user if not found (matched by `slack_user_id` or derived username);
- updates `email`, `display_name`, `slack_user_id`, `is_admin=True` for existing users;
- skips bots and deleted Slack accounts.

Re-running the command is safe — existing users are updated, not duplicated.

## Step 3. Add users to the group

Open:

```text
Administration -> Groups
```

Use `Add user to group`.

Example:

```text
Group: Production
User: ivan
Role: rw
```

Repeat for all users. You can view group members on the same page by clicking `Members` next to the group.

## Step 4. Create a team

Open:

```text
Teams
```

Create a team:

```text
Group: Production
Slug: infra
Name: Infrastructure
Escalate after reminders: 2
```

`Escalate after reminders` means how many reminder messages are sent before the alert is assigned to the next on-call user.

## Step 5. Add users to the team

Open:

```text
Teams
```

Click `Members` next to the team. Use `Add user to selected team`.

Example:

```text
User: ivan
Role: rw
```

Repeat for all users who should participate in the team schedule.

## Step 6. Create a rotation

Open:

```text
Rotations
```

Create a rotation:

```text
Team: infra
Name: infra-primary
Type: daily
Handoff time: 09:00
Timezone: UTC or your team timezone
Reminder interval: 300 seconds
```

A rotation is the calendar object used by routes, services and alerts. When a rotation is created, Beacon creates a `Default layer` inside it.

If `Add all active team members to this rotation` is enabled, all active team members are added to the default layer in team order.

## Step 7. Configure rotation layers

Open:

```text
Rotations -> Layers
```

A layer defines who rotates, when the handoff happens and when the layer is active.

For a simple 24/7 schedule, keep the default layer and add users:

```text
Position 0: ivan
Position 1: petr
Position 2: sergey
```

For business hours, nights and weekends, create separate layers:

```text
Layer: Business hours
Priority: 10
Active: Monday-Friday 09:00-18:00

Layer: Nights
Priority: 20
Active: Monday-Friday 18:00-09:00

Layer: Weekend
Priority: 30
Active: Saturday-Sunday 00:00-00:00
```

Higher priority active layers override lower priority active layers.

If a layer has no restrictions, it is active 24/7.

## Step 8. Verify the calendar

Open:

```text
Calendar
```

Check that the final schedule looks correct. The calendar displays one rotation calendar at a time. If a team has multiple rotations, select the required rotation.

The calendar uses the final schedule:

```text
override > highest-priority active layer > no assignment
```

## Step 9. Create a service

Open:

```text
Services
```

Create a service:

```text
Team: infra
Slug: rabbitmq-cloud
Name: RabbitMQ Cloud
Type: queue
Environment: production
Criticality: critical
Tier: tier_1
Status: operational
```

A service describes the affected system. Routes receive alerts, but services explain what system is broken.

Optional but recommended service context:

```text
Dashboard link: https://grafana.example.com/d/rabbitmq-cloud
Logs link: https://logs.example.com/rabbitmq-cloud
Runbook: https://docs.example.com/runbooks/rabbitmq
```

Service links are stable URLs for the whole service. Runbooks can be generic for the whole service or matched to a specific alert.

Display order in the UI and notifications:

```text
name -> slug -> "-"
```

## Step 10. Create a notification channel

Open:

```text
Channels
```

Select:

```text
Group: Production
Team: infra
```

Create a channel, for example Mattermost Bot API mode:

```text
Type: mattermost
Mode: Bot API with buttons and message updates
Mattermost URL: https://mattermost.example.com
Bot token:
Channel ID:
Callback secret: optional
```

Channels do not have alert intake tokens. They only define where notifications are sent.

### Optional: enable browser push for responders

Browser push is not a channel. It is enabled by each user in Profile and is delivered to that user's browser/PWA devices when an alert is assigned to them.

Open:

```text
Profile
```

Use `Enable push on this device`, allow browser notifications, then use `Send test push`.

Read more: [Browser Push](../usage/browser-push.md).

## Step 11. Create a route

Open:

```text
Routes
```

Create a route:

```text
Team: infra
Source: alertmanager
Rotation: infra-primary
Default service: RabbitMQ Cloud
Channels: infra-mattermost
Matchers JSON: {"labels": {"team": "infra"}}
Group by JSON: ["alertname", "instance"]
```

Copy the route intake token after creating the route. If a route token is lost, open Routes and click `Regenerate token` next to the route.

Use `Default service` when all alerts that enter the route belong to one logical system.

If one route receives alerts for multiple systems, create service match rules.

Example RabbitMQ service match rule:

```json
{
  "labels": {
    "job": "RabbitMQ",
    "rabbitmq": {
      "op": "regex",
      "value": "^rabbitmq-cloud$"
    }
  }
}
```

## Step 12. Send a test alert

Example Alertmanager request:

```bash
curl -X POST http://127.0.0.1:8080/api/integrations/alertmanager \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer ALERTMANAGER_ROUTE_TOKEN' \
  -d '{
    "status": "firing",
    "alerts": [
      {
        "status": "firing",
        "labels": {
          "alertname": "RabbitMQClusterPartition",
          "severity": "critical",
          "team": "infra",
          "job": "RabbitMQ",
          "rabbitmq": "rabbitmq-cloud",
          "instance": "rabbit-1"
        },
        "annotations": {
          "summary": "RabbitMQ cluster partition detected",
          "description": "Erlang distribution link is not healthy"
        },
        "fingerprint": "rabbitmq-cloud-partition-rabbit-1"
      }
    ]
  }'
```

Open `Alerts` and verify that the alert was routed to the expected team, service and on-call user.

## Step 13. Acknowledge or resolve the alert

Open:

```text
Alerts
```

Use:

```text
Acknowledge
Resolve
```

When the alert is attached to a service, alert details and notifications can include service links and matching runbooks.
