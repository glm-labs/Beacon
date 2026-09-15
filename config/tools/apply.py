#!/usr/bin/env python3
"""Config-as-code reconciler for Beacon channels and routes.

Same shape as Upgreat-AI/zabbix's own config/ layer: declarative YAML
under vars/, applied against the app's own API by a small script, run by
CI on merge (deploy) and as a read-only check on PR (validate). Unlike
Zabbix's Ansible-based layer, this one is a single Python file against
Beacon's REST API -- there's no Ansible collection for a from-scratch app,
and the API surface here is small enough not to need one.

Usage:
    BEACON_API_URL=... BEACON_API_TOKEN=... python3 config/tools/apply.py
    python3 config/tools/apply.py --check   # resolve + validate only, no writes

Secrets are never read from these YAML files directly -- see the `*_env`
convention documented in vars/channels.yaml and vars/routes.yaml. A
missing env var fails loudly rather than applying an empty secret.
"""

import argparse
import os
import pathlib
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from beacon_api import api  # noqa: E402


VARS_DIR = pathlib.Path(__file__).resolve().parent.parent / "vars"


def load_vars(filename):
    path = VARS_DIR / filename
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def resolve_env_fields(config):
    """Replace every `<key>_env` entry with the named env var's value.

    Fails loudly (mandatory lookup) rather than writing an empty secret --
    same convention as PUSHOVER_TOKEN's `| mandatory` in the zabbix repo.
    """
    resolved = {}

    for key, value in (config or {}).items():
        if key.endswith("_env"):
            real_key = key[: -len("_env")]
            env_name = value
            env_value = os.environ.get(env_name)

            if not env_value:
                sys.exit(
                    f"config error: environment variable {env_name!r} "
                    f"(for {real_key!r}) is not set"
                )

            resolved[real_key] = env_value
        else:
            resolved[key] = value

    return resolved


def index_by(items, key):
    return {item[key]: item for item in items}


def find_team_id(teams_by_slug, team_slug):
    team = teams_by_slug.get(team_slug)
    if not team:
        sys.exit(
            f"config error: team_slug {team_slug!r} does not exist in Beacon "
            "-- create it first, teams are not managed by this tool"
        )
    return team["id"]


def apply_channels(defs, teams_by_slug, *, check_only):
    channel_ids_by_team_and_name = {}

    for entry in defs:
        team_id = find_team_id(teams_by_slug, entry["team_slug"])
        name = entry["name"]
        config = resolve_env_fields(entry.get("config") or {})

        existing = index_by(
            api("GET", f"/api/channels?team_id={team_id}"), "name"
        ).get(name)

        body = {
            "team_id": team_id,
            "name": name,
            "channel_type": entry["channel_type"],
            "enabled": entry.get("enabled", True),
            "config": config,
        }

        if existing:
            channel_ids_by_team_and_name[(entry["team_slug"], name)] = existing["id"]
            print(f"channel {name!r} (team {entry['team_slug']!r}): would update" if check_only else f"channel {name!r} (team {entry['team_slug']!r}): updating")
            if not check_only:
                api("PUT", f"/api/channels/{existing['id']}", body)
        else:
            print(f"channel {name!r} (team {entry['team_slug']!r}): would create" if check_only else f"channel {name!r} (team {entry['team_slug']!r}): creating")
            if check_only:
                # Nothing was actually created, but a route below may still
                # reference this channel by name -- a placeholder lets
                # --check validate that reference instead of treating a
                # perfectly normal "everything is new" PR as an error.
                channel_ids_by_team_and_name[(entry["team_slug"], name)] = "pending-create"
            else:
                created = api("POST", "/api/channels", body)
                channel_ids_by_team_and_name[(entry["team_slug"], name)] = created["id"]

    return channel_ids_by_team_and_name


def apply_routes(defs, teams_by_slug, channel_ids_by_team_and_name, *, check_only):
    for entry in defs:
        team_slug = entry["team_slug"]
        team_id = find_team_id(teams_by_slug, team_slug)
        name = entry["name"]

        channel_ids = []
        for channel_name in entry.get("channel_names") or []:
            channel_id = channel_ids_by_team_and_name.get((team_slug, channel_name))
            if not channel_id:
                sys.exit(
                    f"config error: route {name!r} references channel "
                    f"{channel_name!r} on team {team_slug!r}, which is not "
                    "defined in vars/channels.yaml"
                )
            channel_ids.append(channel_id)

        integration_config = {
            source: resolve_env_fields(fields)
            for source, fields in (entry.get("integration_config") or {}).items()
        }

        existing = index_by(
            api("GET", f"/api/routes?team_id={team_id}"), "name"
        ).get(name)

        body = {
            "team_id": team_id,
            "name": name,
            "source": entry["source"],
            "channel_ids": channel_ids,
            "integration_config": integration_config,
            "enabled": entry.get("enabled", True),
        }

        if existing:
            print(f"route {name!r} (team {team_slug!r}): would update" if check_only else f"route {name!r} (team {team_slug!r}): updating")
            if not check_only:
                api("PUT", f"/api/routes/{existing['id']}", body)
        else:
            print(f"route {name!r} (team {team_slug!r}): would create" if check_only else f"route {name!r} (team {team_slug!r}): creating")
            if not check_only:
                api("POST", "/api/routes", body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="resolve and validate vars/ without writing anything",
    )
    args = parser.parse_args()

    teams_by_slug = index_by(api("GET", "/api/teams"), "slug")

    channel_ids_by_team_and_name = apply_channels(
        load_vars("channels.yaml").get("channels", []),
        teams_by_slug,
        check_only=args.check,
    )

    apply_routes(
        load_vars("routes.yaml").get("routes", []),
        teams_by_slug,
        channel_ids_by_team_and_name,
        check_only=args.check,
    )


if __name__ == "__main__":
    main()
