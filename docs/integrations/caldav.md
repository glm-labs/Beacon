---
title: CalDAV calendar sync
description: Read-only CalDAV sync for Beacon team on-call schedules.
---

# CalDAV calendar sync

Beacon can expose team on-call schedules as read-only CalDAV calendars. This is useful for calendar clients that support CalDAV directly, such as Apple Calendar, Thunderbird and DAVx5.

Each accessible team is exposed as a separate calendar. Users only see calendars for teams they are allowed to read.

## When to use CalDAV

Use CalDAV when the calendar client supports CalDAV accounts and you want automatic discovery of all accessible team calendars.

Recommended clients:

| Client | Recommended method |
|---|---|
| Apple Calendar on macOS | CalDAV |
| Apple Calendar on iOS/iPadOS | CalDAV |
| Thunderbird | CalDAV |
| DAVx5 on Android | CalDAV |
| Outlook | ICS subscription instead |
| Google Calendar | ICS subscription instead |

For Outlook and Google Calendar, use [ICS calendar feeds](ics-calendar-feed.md).

## Requirements

- Beacon must be reachable over HTTPS from the calendar client.
- The user must have access to at least one team calendar.
- The user must create a personal API token with the `calendar:read` scope.
- The user must use the personal API token as the CalDAV password.

Do not use the user's normal Beacon password for CalDAV.

## Create a CalDAV API token

1. Open **Profile**.
2. Open the **API tokens** tab.
3. Create a new token.
4. Use a clear name, for example `caldav-calendar`.
5. Select the `calendar:read` scope.
6. Copy the generated token.

The token is shown only once. If it is lost, revoke it and create a new one.

## CalDAV URL

Use the base CalDAV endpoint:

```text
https://beacon.example.com/caldav/
```

Replace `beacon.example.com` with your Beacon hostname.

Do not use a direct team calendar path during Apple Calendar account setup. Apple Calendar should discover calendars through the CalDAV root endpoint.

## Apple Calendar on macOS

Open **Calendar → Add Account → Other CalDAV Account → Advanced**.

Use these values:

```text
Account Type: Advanced
User Name: your Beacon username or email
Password: personal API token with calendar:read
Server Address: beacon.example.com
Server Path: /caldav/
Port: 443
Use SSL: enabled
```

Important: the **Server Address** field must contain only the hostname. Do not include `https://` there.

Correct:

```text
beacon.example.com
```

Incorrect:

```text
https://beacon.example.com
```

## Apple Calendar on iOS or iPadOS

Open **Settings → Calendar → Accounts → Add Account → Other → Add CalDAV Account**.

Use:

```text
Server: beacon.example.com
User Name: your Beacon username or email
Password: personal API token with calendar:read
Description: Beacon
```

If the client asks for advanced settings, use:

```text
Server Path: /caldav/
Port: 443
Use SSL: enabled
```

## Thunderbird

1. Open **Calendar**.
2. Choose **New Calendar**.
3. Select **On the Network**.
4. Enter the CalDAV URL:

```text
https://beacon.example.com/caldav/
```

5. Use your Beacon username or email.
6. Use the personal API token as the password.
7. Select the team calendars you want to subscribe to.

## DAVx5 on Android

1. Add a new account in DAVx5.
2. Choose login with URL and user name.
3. Use:

```text
Base URL: https://beacon.example.com/caldav/
User name: your Beacon username or email
Password: personal API token with calendar:read
```

4. Select the team calendars to sync.

## Read-only behavior

Beacon CalDAV calendars are read-only.

Allowed operations:

```text
OPTIONS
PROPFIND
REPORT
GET
HEAD
PROPPATCH as no-op for client-side calendar metadata
```

Rejected operations:

```text
PUT
DELETE
MKCALENDAR
```

Some clients, especially Apple Calendar, may send `PROPPATCH` to store local calendar properties such as color, display name or order. Beacon accepts these requests as no-op so that read-only calendar refresh continues to work.

## Troubleshooting

### Authentication fails

Check that:

- the username is the Beacon username or email;
- the password is a personal API token, not the user password;
- the token has the `calendar:read` scope;
- the token is not revoked or expired;
- the user is active.

You can test authentication with curl:

```bash
curl -i \
  -u 'user@example.com:PERSONAL_API_TOKEN' \
  -X PROPFIND \
  -H 'Depth: 0' \
  https://beacon.example.com/caldav/
```

A successful response should be `207 Multi-Status`.

### Apple Calendar says "No calendar home was specified"

Use the CalDAV root endpoint as the server path:

```text
/caldav/
```

Do not use a direct team path during account setup.

### Apple Calendar says access is not permitted

Check the server logs for `PROPPATCH` or `REPORT` responses. Apple Calendar expects successful WebDAV responses for some metadata operations even when the calendar itself is read-only.

Expected behavior:

```text
PROPPATCH /caldav/calendars/teams/<team_id>/ -> 207
REPORT    /caldav/calendars/teams/<team_id>/ -> 207
```

### Login succeeds but no calendars appear

Check that the user has access to at least one active team. The user must be allowed to read the team calendar.

Also check that the team and its group are active.

### Events do not appear

Check that the team has rotations and future on-call slots. A team without rotations can still be discovered as an empty calendar.

Use curl to inspect the calendar home:

```bash
curl -i \
  -u 'user@example.com:PERSONAL_API_TOKEN' \
  -X PROPFIND \
  -H 'Depth: 1' \
  https://beacon.example.com/caldav/calendars/
```

The response should include calendar hrefs like:

```text
/caldav/calendars/teams/1/
```

## Security notes

- CalDAV uses HTTP Basic Auth with a personal API token.
- The `calendar:read` scope is enough for calendar sync.
- Revoke the token from Profile to stop CalDAV access.
- Do not log the `Authorization` header.
- Do not expose CalDAV over plain HTTP in production.
- CalDAV does not allow users to edit Beacon schedules from external calendar clients.
