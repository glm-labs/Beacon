import pytest

from app.settings import Settings


def write_config(path, body: str):
    path.write_text(body, encoding="utf-8")
    return path


def test_settings_read_basic_types(tmp_path):
    config_path = write_config(
        tmp_path / "beacon.conf",
        """
[main]
name = Beacon
enabled = true
count = 7
items = ["a", "b"]
""",
    )

    settings = Settings(str(config_path))

    assert settings.get("main", "name") == "Beacon"
    assert settings.get_bool("main", "enabled") is True
    assert settings.get_int("main", "count") == 7
    assert settings.get_json("main", "items") == ["a", "b"]


def test_settings_returns_defaults_for_missing_values(tmp_path):
    config_path = write_config(
        tmp_path / "beacon.conf",
        """
[main]
name = Beacon
""",
    )

    settings = Settings(str(config_path))

    assert settings.get("missing", "value", "fallback") == "fallback"
    assert settings.get_int("missing", "value", 15) == 15
    assert settings.get_bool("missing", "value", True) is True
    assert settings.get_json("missing", "value", {"x": 1}) == {"x": 1}
    assert settings.get_section("missing", {"fallback": "yes"}) == {"fallback": "yes"}


def test_settings_invalid_json_raises_runtime_error(tmp_path):
    config_path = write_config(
        tmp_path / "beacon.conf",
        """
[main]
bad_json = {invalid}
""",
    )

    settings = Settings(str(config_path))

    with pytest.raises(RuntimeError):
        settings.get_json("main", "bad_json")
