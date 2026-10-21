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
- `sound_map` — optional, a Pushover sound per severity for this
  channel, for example `{"critical": "persistent"}`. Overrides the
  app-wide `[pushover] sounds` (see [Sounds](#sounds)) for the severities
  it names.
- `callback_secret` — optional per-channel override of the app-wide
  `[pushover] action_secret` used to sign the acknowledge callback URL
  (see below). Only needed if you want a channel's callback signed with a
  different secret than every other channel.

`notify_on_severities`, same as every other channel type, filters which
severities this channel receives at all — see [Notification
Policies](../usage/notification-policies.md).

## Personal notification rule

A user's own Pushover user key lives on their profile (`pushover_user_key`),
set from **Profile → Profile → Contact IDs**, next to the Telegram, Slack and
Mattermost user IDs. An admin can set it for someone else from **Admin →
Users**. A personal Pushover rule
always uses the app-wide `[pushover] app_token` — there's no per-rule
app_token field, since a personal rule has nowhere to put one.

Users who never make a rule can still be paged by Pushover through
`[notifications] default_rules`, for everyone whose profile has a Pushover
user key. See [Default notification rules](../getting-started/configuration.md#default-notification-rules).

## Sounds

Without a `sound`, Pushover plays the receiving device's default sound,
which is the same short chime for every priority. A page that has to wake
someone can carry its own sound, set per severity:

```ini
[pushover]
sounds = {"critical": "persistent", "high": "siren"}
```

- Applies to every Pushover send: shared channels and personal
  notification rules alike. A channel's `sound_map` overrides it per
  severity.
- Values are Pushover sound names: a built-in one (`pushover`, `siren`,
  `spacealarm`, the long `persistent`, `echo`, `alien`, `climb` and
  `updown`, `vibrate`, `none`, ...) or a custom sound uploaded to the
  receiving Pushover account. The full list for your application is at
  `https://api.pushover.net/1/sounds.json?token=<app token>`.
- A severity that is not listed plays the device default.
- Acknowledged and resolved updates are sent at priority -1 and never
  carry a sound.
- On a critical (priority 2) alert the sound plays again on every `retry`.
  On iOS it only breaks through Focus and silent mode when the user has
  allowed Critical Alerts for the Pushover app.

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
5. A tap that arrives after the alert resolved changes nothing: the alert
   stays resolved, nothing is written back to the source, and the callback
   answers `already_resolved`. The page can still be on the phone after
   the recovery, and acknowledging it would reopen an alert that no
   recovery will close again.

Acknowledging is not resolving: the notification's priority immediately
drops (event_type `acknowledged`/`resolved` always sends at priority -1,
never re-triggering emergency behavior), but the underlying alert is only
resolved the normal way — the source clears, or a person resolves it.

## Stopping the other phones

Tapping Acknowledge stops the message it belongs to, and no other.
Everyone a team rule or a rotation pages gets a message of their own, and
each one keeps
repeating every `retry` seconds until its own recipient taps it or
`expire` passes. So Beacon tags every emergency message with its alert
(`beacon-alert-<id>`), and the moment the alert stops firing it cancels the
retries of every message with that tag through Pushover's
`receipts/cancel_by_tag`:

- acknowledged anywhere: the Pushover button, the UI, the API, Slack, ...;
- resolved, by the source's recovery or by a person;
- snoozed.

That is one request per app token that sent the alert an emergency
message: the app-wide `[pushover] app_token` for notification rules, and
each Pushover channel's own token. The alert timeline shows "Stopped N
emergency Pushover page(s)". When the request fails, the acknowledge,
resolve or snooze still stands, and the timeline records
`pushover_emergency_cancel_failed`: those messages then repeat until they
are acknowledged on the phone or expire.

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
