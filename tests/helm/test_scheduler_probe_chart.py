import os
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "helm" / "beacon"

pytestmark = pytest.mark.skipif(shutil.which("helm") is None, reason="helm is not installed")


def _render_scheduler(tmp_path, extra_values=""):
    values = tmp_path / "values.yaml"
    values.write_text(
        textwrap.dedent(
            """\
            config:
              main:
                secret_key: test-secret-key-for-helm-rendering
            """
        )
        + textwrap.dedent(extra_values),
        encoding="utf-8",
    )
    return subprocess.check_output(
        [
            "helm", "template", "beacon", str(CHART),
            "-f", str(values),
            "--show-only", "templates/deployment-scheduler.yaml",
        ],
        text=True,
    )


def _probe_script(rendered):
    """Return the python -c script of the rendered liveness probe."""
    lines = rendered.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == "- >-")
    script = []
    for line in lines[start + 1:]:
        if line.strip().startswith("initialDelaySeconds:"):
            break
        script.append(line.strip())
    return " ".join(script)


def test_scheduler_gets_a_liveness_probe_on_the_alive_file(tmp_path):
    rendered = _render_scheduler(tmp_path)

    assert "livenessProbe:" in rendered
    assert '"/var/lib/beacon/scheduler.alive"' in _probe_script(rendered)
    assert "< 90 else 1" in _probe_script(rendered)
    assert "failureThreshold: 3" in rendered


def test_the_probe_passes_on_a_fresh_file_and_fails_on_a_stale_or_missing_one(tmp_path):
    alive = tmp_path / "scheduler.alive"
    rendered = _render_scheduler(
        tmp_path,
        f"""\
        scheduler:
          livenessProbe:
            path: {alive}
        """,
    )
    script = _probe_script(rendered)

    def probe():
        return subprocess.run([sys.executable, "-c", script]).returncode

    assert probe() != 0

    alive.touch()
    assert probe() == 0

    stale = time.time() - 120
    os.utime(alive, (stale, stale))
    assert probe() != 0


def test_the_probe_can_be_turned_off(tmp_path):
    rendered = _render_scheduler(
        tmp_path,
        """\
        scheduler:
          livenessProbe:
            enabled: false
        """,
    )

    assert "livenessProbe:" not in rendered
