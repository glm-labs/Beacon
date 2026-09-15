---
title: ICS calendar feeds
description: Tokenized ICS subscription feeds for Beacon team on-call schedules.
---

# ICS calendar feeds

Beacon can generate tokenized ICS subscription feeds for team on-call schedules. This is useful for calendar clients that do not support CalDAV well, especially Outlook and Google Calendar.

An ICS feed is a secret URL ending with `.ics`. Anyone with the URL can read that team's exported on-call calendar, so treat the URL like a password.

## When to use ICS feeds

Use ICS feeds for clients that support subscribing to an internet calendar URL.

| Client | Recommended method |
|---|---|
| Outlook on the web | ICS subscription |
| New Outlook | ICS subscription |
| Google Calendar | ICS subscription |
| Apple Calendar | CalDAV preferred |
| Thunderbird | CalDAV or ICS |

For Apple Calendar, Thunderbird and DAVx5, see [CalDAV calendar sync](caldav.md).

## Create an ICS feed

1. Open **Calendar**.
2. Select a specific team. Export is not available for the "all teams" view.
3. Click **Export**.
4. Create a feed if one does not already exist.
5. Copy the generated feed URL.

The feed URL looks like this:

```text
https://beacon.example.com/api/calendar/feeds/<secret-token>.ics
```

The token is shown when the feed is created or regenerated. Existing feed list responses should not expose the token again.

## Subscribe from Outlook

In Outlook on the web or new Outlook:

1. Open **Calendar**.
2. Choose **Add calendar**.
3. Choose **Subscribe from web**.
4. Paste the Beacon `.ics` URL.
5. Choose a name and color.
6. Save.

Outlook refresh frequency is controlled by Outlook and may not be immediate.

## Subscribe from Google Calendar

In Google Calendar:

1. Open **Other calendars**.
2. Click **+**.
3. Choose **From URL**.
4. Paste the Beacon `.ics` URL.
5. Click **Add calendar**.

Google Calendar refresh frequency is controlled by Google and may take time.

## Subscribe from Apple Calendar using ICS

CalDAV is recommended for Apple Calendar, but an ICS subscription can also be used.

On macOS:

1. Open **Calendar**.
2. Choose **File → New Calendar Subscription**.
3. Paste the Beacon `.ics` URL.
4. Configure auto-refresh.

If you want automatic discovery of all accessible teams, use CalDAV instead.

## Feed management

### Regenerate token

Regenerating a feed token creates a new secret URL and immediately invalidates the old URL.

Use this when:

- the URL was shared with the wrong person;
- the URL may have leaked;
- a user who had the URL should no longer be able to use it.

After regeneration, update calendar subscriptions with the new URL.

### Delete feed

Deleting a feed disables the subscription URL. Calendar clients using the old URL will stop refreshing successfully.

### Inactive team or group

If the team or its group becomes inactive, the feed returns `403 Forbidden`.

## API endpoints

Management endpoints require normal Beacon API authentication and permissions.

```text
GET    /api/calendar/feeds?team_id=<team_id>
POST   /api/calendar/feeds
POST   /api/calendar/feeds/<feed_id>/token
DELETE /api/calendar/feeds/<feed_id>
```

The subscription endpoint is public but protected by the secret token in the URL:

```text
GET /api/calendar/feeds/<secret-token>.ics
```

Only the `.ics` subscription endpoint should be public. Do not make all `/api/calendar/feeds/` endpoints public.

## Example API usage

Create a feed:

```bash
curl -s \
  -X POST \
  -H 'Authorization: Bearer BEACON_API_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"team_id":1,"name":"Cloud OPS subscription","past_days":7,"future_days":90}' \
  https://beacon.example.com/api/calendar/feeds
```

Download the feed:

```bash
curl -i https://beacon.example.com/api/calendar/feeds/<secret-token>.ics
```

A successful response should have:

```text
Content-Type: text/calendar
Cache-Control: no-store
```

## Security notes

- The feed URL is a bearer secret.
- Anyone with the `.ics` URL can read the exported team calendar.
- Use HTTPS in production.
- Regenerate the token if the URL leaks.
- Delete the feed to disable the URL completely.
- Do not log full feed tokens.
- Do not expose tokenized URLs in public issue trackers, chat rooms or screenshots.

## Troubleshooting

### Calendar client says the URL is invalid

Check that the URL ends with `.ics` and is reachable from the client network.

```text
https://beacon.example.com/api/calendar/feeds/<secret-token>.ics
```

### Feed returns 404

The token is invalid, regenerated, deleted or copied incorrectly.

Create a new feed or regenerate the token.

### Feed returns 403

The feed exists, but the team or group is inactive.

Reactivate the team/group or create a feed for an active team.

### Events do not update immediately

Outlook and Google Calendar control their own refresh intervals. Beacon returns the current ICS content, but the external service may cache the subscription.

### Feed is empty

The team may have no rotations or no generated on-call slots in the configured export range.

Check the feed settings:

```text
past_days
future_days
```

Increase `future_days` if the exported range is too short.
