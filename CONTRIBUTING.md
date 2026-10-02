## Backend changes policy

Any backend code change must be covered by tests.

When changing backend logic:
- add new tests for new behavior;
- update existing tests for changed behavior;
- do not remove failing tests unless the tested behavior was intentionally removed;
- if a backend change does not need tests, explain why in the pull request.

## Upstream code

Beacon is MIT licensed and forked from IncidentRelay before it moved to the
Elastic License 2.0. Never copy or adapt code, tests, docs or translations
from IncidentRelay after the fork point; [NOTICE.md](NOTICE.md) has the
details.
