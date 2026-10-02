# Notice

Beacon is licensed under the [Elastic License 2.0](LICENSE) (ELv2). In
short: you may use, run, modify and redistribute it, including inside a
company, but you may not offer it to third parties as a hosted or managed
service. The [LICENSE](LICENSE) file has the binding terms.

## Where Beacon comes from

Beacon started as a fork of [IncidentRelay](https://github.com/roxy-wi/IncidentRelay)
by roxy-wi. The fork point is upstream commit
`7536833e5f031332716f5f50f1ef98410f76d386` ("Harden soft-delete lifecycle and
resource restoration", 6 September 2026), the last upstream commit published
under the MIT License. Its history is kept in this repository.

The code Beacon took from IncidentRelay remains available under the MIT
License that came with it. Its copyright and permission notice are reproduced
in [licenses/IncidentRelay-MIT.txt](licenses/IncidentRelay-MIT.txt), as that
license requires. Everything Beacon added or changed on top of the fork point
is offered under ELv2 only, and Beacon as a whole is distributed under ELv2.

Beacon does not contain IncidentRelay code from after the fork point.
IncidentRelay moved to ELv2 in its next commit; features that upstream added
later either do not exist here or were written independently for Beacon:

- alert snooze (`app/services/alerts/snooze.py`), Beacon's own take on pausing
  a firing alert;
- SSO contact claims (`app/modules/sso/contact_claims.py`), which fill a user's
  messenger IDs and Pushover key from identity-provider claims.

## Rule for contributors

Do not copy, port or adapt code, tests, documentation or translations from
IncidentRelay commits after the fork point above. If upstream fixed a bug
that also exists here, reproduce it and fix it from the behaviour, not from
their patch.

Contributions to Beacon are accepted under the same terms as the rest of
Beacon (ELv2).
