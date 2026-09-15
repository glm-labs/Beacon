import os


_CONFIG_ENV = "BEACON_CONFIG_FILE"
_DEFAULT_CONFIG_PATH = "/etc/beacon/beacon.conf"


def _resolve_config_path():
    """Return the configured config file path."""
    return os.getenv(_CONFIG_ENV) or _DEFAULT_CONFIG_PATH


CONFIG_FILE = _resolve_config_path()
