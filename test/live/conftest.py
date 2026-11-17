"""GOV-004 live replay configuration.

Kept separate from ``tests/conftest.py`` on purpose: the upstream conftest blanks
every ``TRADINGAGENTS_*`` setting and blocks sockets, which is exactly what a
live run must NOT do. This directory is also outside ``testpaths`` so the
ordinary suite never runs it.

Two suites live here:

* ``test_harness_selfcheck.py`` -- offline harness verification (scripted
  model, no network). Always runnable.
* ``test_gov004_live.py`` -- the real live replay. It runs only when the
  operator opts in explicitly (``GOV004_LIVE=1``), so an accidental full-suite
  invocation never spends provider budget.
"""

from __future__ import annotations

import os

import pytest


def pytest_configure(config):
    for marker in ("unit", "integration", "smoke", "live"):
        config.addinivalue_line("markers", f"{marker}: {marker}-level tests")
    config.addinivalue_line(
        "markers", "live: makes real provider calls; requires GOV004_LIVE=1"
    )


def live_enabled() -> bool:
    return os.getenv("GOV004_LIVE", "").strip() == "1"


def pytest_collection_modifyitems(config, items):
    """Skip the live test unless the explicit opt-in is set."""
    if live_enabled():
        return
    skip_live = pytest.mark.skip(
        reason="GOV004_LIVE not set; live semantic replay is opt-in (set GOV004_LIVE=1)."
    )
    for item in items:
        if item.get_closest_marker("live"):
            item.add_marker(skip_live)
