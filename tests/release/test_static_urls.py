"""Guards for how templates link static assets.

`url_for("static", filename="/css/...")` renders `/static//css/...`. The
server answers that with a redirect to the merged path, and behind a TLS
proxy that redirect points at http://, which browsers block as mixed
content on an https page. Font Awesome was linked that way, so every icon
rendered as an empty box.
"""

from __future__ import annotations

import re
from pathlib import Path


TEMPLATES = Path("app/templates")
LEADING_SLASH = re.compile(r"""url_for\(\s*['"]static['"]\s*,\s*filename\s*=\s*['"]/""")


def test_no_template_links_a_static_file_with_a_leading_slash():
    offenders = [
        f"{path}:{number}"
        for path in sorted(TEMPLATES.rglob("*.html"))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if LEADING_SLASH.search(line)
    ]

    assert not offenders, "static filename must not start with '/': " + ", ".join(offenders)


def test_login_page_links_font_awesome_without_a_double_slash(client):
    html = client.get("/login").get_data(as_text=True)

    assert 'href="/static/css/vendor/fontawesome/all.min.css"' in html
    assert "/static//" not in html
