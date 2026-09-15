---
title: Pushover Channel
description: Pushover notification setup, priority mapping, and 1-tap acknowledge.
---

# Pushover channel

Pushover is an outgoing notification channel, and can also be used as a
personal notification rule (Profile → Notification rules) alongside email
and voice call.

Unlike Slack/Mattermost/Telegram, Pushover has no custom interactive
buttons: on a **critical**-severity alert (Pushover priority 2, "emergency"),
Pushover puts its own built-in **Acknowledge** button in the notification
and keeps re-alerting every `retry` seconds until someone taps it or
`expire` seconds pass. Beacon wires that button straight back into the same
`acknowledge_alert()` a Slack or Mattermost button click uses, so an
emergency page can be acknowledged from the notification itself, without
opening Beacon.

## Shared channel config

```json
{
  "app_token": "a...",
  "target": "g...",
  "priority_map": {
    "critical": 2,
    "high": 1,
    "medium": 0,
    "warning": 0,
    "low": -1,
    "info": -1
  }
}
```

- `app_token` — a Pushover application token. Optional on the channel: if
  omitted, the app-wide `[pushover] app_token` from the config file is
  used instead (same relationship as one SMTP server sending for many
  channels). The notifier raises a clear error at send time if neither is
  set.
- `target` — required. A Pushover **user key** pages one person; a
  Pushover **delivery group key** pages everyone in that group, which is
  the usual choice for an on-call rotation channel so escalation doesn't
  depend on one person's device.
- `priority_map` — optional, overrides the defaults shown above. Values
  must be Pushover priorities, `-2` to `2`. Only alerts that normalize to
  severity `critical` reach priority 2 by default; see
  `app/services/severity.py` for the full severity vocabulary.
- `callback_secret` — optional per-channel override of the app-wide
  `[pushover] action_secret` used to sign the acknowledge callback URL
  (see below). Only needed if you want a channel's callback signed with a
  different secret than every other channel.

`notify_on_severities`, same as every other channel type, filters which
severities this channel receives at all — see [Notification
Policies](../usage/notification-policies.md).

## Personal notification rule

A user's own Pushover user key lives on their profile (`pushover_user_key`),
set from **Profile → Notification settings**. A personal Pushover rule
always uses the app-wide `[pushover] app_token` — there's no per-rule
app_token field, since a personal rule has nowhere to put one.

## 1-tap acknowledge

Requires `[server] public_base_url` to be set to a URL Pushover's servers
can reach, and `[pushover] action_secret` to be set (falls back to
`[main] secret_key` if unset, but a dedicated secret is recommended — same
reasoning as `[mattermost] action_secret`).

What actually happens on a critical alert:

1. Beacon sends the Pushover message with `priority: 2`, `retry`, `expire`,
   and a `callback` URL that embeds the alert id, channel id, and an HMAC
   signature — the only way to hand Pushover data of our own, since it
   controls the callback POST body, not us.
2. Pushover shows its own Acknowledge button and re-alerts every `retry`
   seconds.
3. Tapping Acknowledge makes Pushover POST once to that `callback` URL.
   Beacon verifies the signature and calls `acknowledge_alert()` — the
   same function a Slack/Mattermost button, the API, or the UI would call.
4. If the acknowledging Pushover user key matches a Beacon user's own
   `pushover_user_key` (and that user can respond for the alert's team),
   the acknowledge is attributed to them. If it doesn't match — very
   common for a shared delivery-group key paging a whole rotation from one
   device — the acknowledge still goes through, just unattributed. A page
   that gets acknowledged by someone Beacon can't name still beats one
   that nags for a full hour because the tap didn't count.

Acknowledging is not resolving: the notification's priority immediately
drops (event_type `acknowledged`/`resolved` always sends at priority -1,
never re-triggering emergency behavior), but the underlying alert is only
resolved the normal way — the source clears, or a person resolves it.

## Acknowledging back to the source system

Some alert sources have their own escalation/nagging that doesn't know
about a Beacon acknowledge. Zabbix does — see [Zabbix
integration](zabbix.md#acknowledge-writeback) for how to configure a route
to also acknowledge the originating Zabbix event, which is what actually
stops Zabbix's own escalation (and, if you're also using Zabbix's native
Pushover mediatype somewhere, that mediatype's own retry) once Beacon has
been acknowledged. This isn't specific to Pushover — it fires from
whatever acknowledged the alert, Pushover included.

## Troubleshooting

Check:

1. Channel is enabled and attached to the matched route.
2. Severity filter (`notify_on_severities`) allows the alert severity.
3. `app_token` resolves to something — channel config or
   `[pushover] app_token`.
4. `target` is a valid Pushover user or delivery-group key.
5. For 1-tap acknowledge: `public_base_url` is reachable from Pushover's
   servers, and `[pushover] action_secret` is set.
6. For source writeback: see [Zabbix
   integration](zabbix.md#acknowledge-writeback) troubleshooting.
