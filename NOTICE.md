# Notice

Beacon started as a fork of [IncidentRelay](https://github.com/roxy-wi/IncidentRelay)
by roxy-wi. The fork point is upstream commit
`7536833e5f031332716f5f50f1ef98410f76d386` ("Harden soft-delete lifecycle and
resource restoration", 6 September 2026), the last upstream commit published
under the MIT License. Its history is kept in this repository, and the
original copyright notice stays in [LICENSE](LICENSE) as MIT requires.

IncidentRelay moved to the Elastic License 2.0 in its next commit. Nothing from
that commit or anything after it is part of Beacon. Features that upstream
added after the fork point either do not exist here or were written
independently for Beacon:

- alert snooze (`app/services/alerts/snooze.py`), Beacon's own take on pausing
  a firing alert;
- SSO contact claims (`app/modules/sso/contact_claims.py`), which fill a user's
  messenger IDs and Pushover key from identity-provider claims.

## Rule for contributors

Do not copy, port or adapt code, tests, documentation or translations from
IncidentRelay commits after the fork point above. If upstream fixed a bug
that also exists here, reproduce it and fix it from the behaviour, not from
their patch.
