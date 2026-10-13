"""Pushover sound selection by alert severity."""

import re

# A Pushover sound name: a built-in one (pushover, siren, persistent, ...)
# or a custom sound uploaded to the receiving Pushover account.
SOUND_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def normalize_sound_map(value):
    """Return a severity -> sound map with valid entries only."""
    if not isinstance(value, dict):
        return {}

    result = {}
    for severity, sound in value.items():
        sound = str(sound or "").strip()
        if SOUND_NAME_PATTERN.match(sound):
            result[str(severity).strip().lower()] = sound

    return result
