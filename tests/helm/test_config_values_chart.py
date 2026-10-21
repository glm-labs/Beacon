from pathlib import Path
import re
import shutil
import subprocess
import textwrap

import pytest


ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "helm" / "beacon"
SCIENTIFIC = re.compile(r"^\s*\w+ = -?\d+(\.\d+)?[eE][+-]?\d+\s*$", re.M)


def _render(tmp_path, values_yaml):
    values = tmp_path / "values.yaml"
    values.write_text(textwrap.dedent(values_yaml), encoding="utf-8")
    return subprocess.check_output(
        ["helm", "template", "beacon", str(CHART), "-f", str(values)],
        text=True,
    )


@pytest.mark.skipif(shutil.which("helm") is None, reason="helm is not installed")
def test_default_config_renders_large_integers_without_exponent(tmp_path):
    rendered = _render(
        tmp_path,
        """\
        config:
          main:
            secret_key: test-secret-key-for-helm-rendering
        """,
    )

    assert "outbound_http_max_response_bytes = 1048576" in rendered
    assert not SCIENTIFIC.findall(rendered)


@pytest.mark.skipif(shutil.which("helm") is None, reason="helm is not installed")
def test_config_values_keep_fractions_strings_and_booleans(tmp_path):
    rendered = _render(
        tmp_path,
        """\
        config:
          main:
            secret_key: test-secret-key-for-helm-rendering
          retention:
            alert_days: 36500000
          sample:
            ratio: 0.25
            label: "1048576"
            enabled: true
        """,
    )

    assert "alert_days = 36500000" in rendered
    assert "ratio = 0.25" in rendered
    assert "label = 1048576" in rendered
    assert "enabled = true" in rendered
    assert not SCIENTIFIC.findall(rendered)


@pytest.mark.skipif(shutil.which("helm") is None, reason="helm is not installed")
def test_config_lists_and_maps_render_as_one_json_line(tmp_path):
    rendered = _render(
        tmp_path,
        """\
        config:
          main:
            secret_key: test-secret-key-for-helm-rendering
          notifications:
            default_rules:
              - method: pushover
                delay_seconds: 600
                severities: [medium, warning]
          pushover:
            sounds:
              critical: persistent
        """,
    )

    assert (
        'default_rules = [{"delay_seconds":600,"method":"pushover","severities":["medium","warning"]}]'
        in rendered
    )
    assert 'sounds = {"critical":"persistent"}' in rendered


def _checksums(rendered):
    return re.findall(r"checksum/config: (\w+)", rendered)


@pytest.mark.skipif(shutil.which("helm") is None, reason="helm is not installed")
def test_existing_config_secret_has_no_checksum_by_default(tmp_path):
    rendered = _render(
        tmp_path,
        """\
        existingConfigSecret: beacon-config
        """,
    )

    assert _checksums(rendered) == []


@pytest.mark.skipif(shutil.which("helm") is None, reason="helm is not installed")
def test_existing_config_secret_from_values_rolls_pods_on_a_config_change(tmp_path):
    def checksums(sounds):
        return _checksums(
            _render(
                tmp_path,
                f"""\
                existingConfigSecret: beacon-config
                existingConfigSecretFromValues: true
                config:
                  main:
                    secret_key: "{{{{ .secret_key }}}}"
                  pushover:
                    sounds: '{sounds}'
                """,
            )
        )

    before = checksums('{"critical": "persistent"}')
    after = checksums('{"critical": "siren"}')

    # web, scheduler, telegram and slack each carry it, all the same.
    assert len(before) == 4 and len(set(before)) == 1
    assert before == checksums('{"critical": "persistent"}')
    assert set(before) != set(after)
