# Beacon config as code

Declarative config for Beacon's channels and routes, applied against its
own REST API. Same shape as `Upgreat-AI/zabbix`'s `config/` layer:
`vars/*.yaml` as the source of truth, one small script that reconciles it,
CI that runs that script on PR (read-only check) and on merge (apply).

The difference from the Zabbix layer is the mechanism, not the philosophy:
Zabbix's is Ansible against a JSON-RPC API because that's what the Zabbix
Ansible collection gives you for free; Beacon has no such collection, and
its REST API is small enough that a single Python file
(`tools/apply.py`, `tools/beacon_api.py`) against `requests`-free stdlib
`urllib` covers it without inventing a bigger framework than the problem
needs.

## Layout

```
config/
  README.md
  requirements.txt      # PyYAML only -- everything else is stdlib
  vars/
    channels.yaml        # notification channels, by (team_slug, name)
    routes.yaml           # alert routes, by (team_slug, name)
  tools/
    beacon_api.py         # ~40-line REST client: env-configured, Bearer auth
    apply.py              # the reconciler
```

Extend this the same way the Zabbix layer grew: one more `vars/*.yaml` plus
one more `apply_*` function in `apply.py` per resource type (teams,
rotations, escalation policies, ...) as the need shows up. Nothing here
assumes only channels and routes exist -- those are just the two pieces
this pass actually needed, for the Pushover channel and the Zabbix route
with acknowledge writeback (see `docs/integrations/pushover.md` and
`docs/integrations/zabbix.md#acknowledge-writeback`).

## Secrets

Never committed in plaintext. A `<key>_env` entry in any `config:` or
`integration_config.<source>:` block names an environment variable;
`apply.py` resolves it at apply time and fails the run loudly if that
variable is unset -- the same "mandatory lookup, no silent empty secret"
rule the Zabbix repo uses for `PUSHOVER_TOKEN`. See `vars/channels.yaml`
and `vars/routes.yaml` for the actual env var names each config expects.

Because the API masks secrets on read (`***`, or Pushover's own
placeholder convention on the channel side), the reconciler can't diff a
stored secret against the desired one -- it always sends the full desired
config on every apply instead. That makes repeated applies of unchanged
config a no-op in effect (same end state), even though it looks like an
"update" in the log every time.

## Running locally

```
python3 -m venv .venv && source .venv/bin/activate
pip install -r config/requirements.txt

export BEACON_API_URL=https://beacon.example.internal
export BEACON_API_TOKEN=...          # see "Which token" below
export PUSHOVER_APP_TOKEN=...
export PUSHOVER_TARGET_GROUP=...
export ZABBIX_ACK_API_TOKEN=...

python3 config/tools/apply.py --check   # resolve + validate, no writes
python3 config/tools/apply.py           # apply
```

### Which token

**Mint the token from an admin user's own Profile page (or `POST
/api/profile/tokens` while authenticated as that user), not
`manage.py create-token`.** Verified end-to-end against a real instance
while building this: a token minted via the `manage.py create-token` CLI
has no associated user, and endpoints like `GET /api/teams` filter by the
*calling user's* team membership -- with no user attached, that filter
sees nobody's teams and returns `[]` regardless of the token's scopes,
even `*`. A profile token inherits the admin's own visibility, which is
what this reconciler actually needs (it has to see every team named in
`vars/*.yaml`, not just one). Required scopes: `teams:read`,
`channels:read`, `channels:write`, `routes:read`, `routes:write` (or `*`).

`--check` still needs a real, reachable Beacon and a valid token: it
validates `team_slug`/`channel_names` references against live state, not
just YAML shape, the same way the Zabbix repo's own `validate.yaml`
workflow runs the real playbook in diff mode rather than a purely static
lint.

## CI

- `.github/workflows/beacon-config-validate.yml` -- runs `apply.py --check`
  on every PR touching `config/`.
- `.github/workflows/beacon-config-deploy.yml` -- runs `apply.py` for real
  on merge to `main`.

Both need `BEACON_API_URL` and `BEACON_API_TOKEN` as repo secrets, plus one
secret per `*_env` reference in `vars/` (`PUSHOVER_APP_TOKEN`,
`PUSHOVER_TARGET_GROUP`, `ZABBIX_ACK_API_TOKEN` today). **None of this can
run yet** -- Beacon has no deployed instance to point `BEACON_API_URL` at.
Once one exists: mint an admin-scoped personal API token from its own
Profile page, set the secrets above, and the next merge to `main` will
apply for real.
