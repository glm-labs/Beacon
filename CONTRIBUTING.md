## Backend changes policy

Any backend code change must be covered by tests.

When changing backend logic:
- add new tests for new behavior;
- update existing tests for changed behavior;
- do not remove failing tests unless the tested behavior was intentionally removed;
- if a backend change does not need tests, explain why in the pull request.

## Upstream code

Beacon is licensed under the Elastic License 2.0 and was forked from
IncidentRelay's last MIT-licensed commit. Never copy or adapt code, tests,
docs or translations from IncidentRelay after that fork point;
[NOTICE.md](NOTICE.md) has the details. Contributions are accepted under
the Elastic License 2.0.
