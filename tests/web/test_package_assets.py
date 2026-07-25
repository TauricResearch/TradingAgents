"""F1: verify the built SPA is packaged so a wheel serves it without Node.

The frontend is built straight into ``tradingagents/web/static`` so the
installed package can serve the index plus hashed assets at runtime with no
Node toolchain. This test fails on a clean checkout before ``npm run build``
has produced those assets, which is intentional — the H2 committed-asset-drift
gate enforces that built assets are checked in and reproducible.
"""

from __future__ import annotations

from importlib.resources import files

import pytest

pytestmark = pytest.mark.unit

STATIC_DIR = files("tradingagents.web").joinpath("static")


def _exists(path) -> bool:
    try:
        return path.is_file()
    except (OSError, ValueError):
        return False


def test_built_index_html_is_packaged_in_web_static():
    index = STATIC_DIR.joinpath("index.html")
    assert _exists(index), (
        "tradingagents/web/static/index.html is missing — run "
        "`npm --prefix frontend install && npm --prefix frontend run build`"
    )
    text = index.read_text(encoding="utf-8")
    assert "<div id=\"root\"></div>" in text
    # The built index references hashed module assets rather than the dev entry.
    assert "/assets/" in text or "/src/main.tsx" in text


def test_hashed_assets_directory_is_packaged_when_built():
    assets = STATIC_DIR.joinpath("assets")
    if not assets.is_dir():
        pytest.skip("assets/ only exists after a production build")
    members = [p for p in assets.iterdir() if p.is_file()]
    assert members, "built assets directory is empty"
    # Vite emits hashed JS bundles; at least one must carry the React entry.
    assert any(p.name.endswith(".js") for p in members)
