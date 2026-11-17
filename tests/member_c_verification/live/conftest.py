"""GOV-004 live replay configuration.

This directory now lives under ``tests/`` (the configured ``testpaths``), so the
upstream ``tests/conftest.py`` applies to it. That upstream conftest blanks every
``TRADINGAGENTS_*`` setting and blocks sockets for tests not marked
``integration`` — exactly what a live run must NOT do. This conftest neutralises
those two behaviours for the ``live`` suite while keeping them for everything
else here.

Two suites live in this directory:

* ``offline`` behaviours and ``test_harness_selfcheck.py`` -- offline, scripted
  model, no network. Always runnable and collected by the default suite.
* ``test_gov004_live.py`` -- the real live replay. It runs only when the
  operator opts in explicitly (``GOV004_LIVE=1``); otherwise it is skipped, so an
  accidental full-suite invocation never spends provider budget or touches the
  network.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]


def pytest_configure(config):
    for marker in ("unit", "integration", "smoke", "live"):
        config.addinivalue_line("markers", f"{marker}: {marker}-level tests")
    config.addinivalue_line(
        "markers", "live: makes real provider calls; requires GOV004_LIVE=1"
    )


def live_enabled() -> bool:
    return os.getenv("GOV004_LIVE", "").strip() == "1"


@pytest.fixture(autouse=True)
def _no_network(request, monkeypatch):
    """Override the upstream socket block for ``live`` tests.

    The upstream ``tests/conftest.py`` defines this autouse fixture to refuse all
    sockets. A live run needs them; a non-live test here keeps the upstream
    protection. Because this fixture shadows the parent's for this directory, we
    re-apply the block ourselves for the non-live case.
    """
    if request.node.get_closest_marker("live") and live_enabled():
        return  # live, opted in: allow the network
    if request.node.get_closest_marker("integration"):
        return

    import socket

    def refuse(*args, **kwargs):
        raise OSError(f"test tried to reach the network: {args[1:] or kwargs}")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: refuse(None, *a))
    try:
        from curl_cffi import requests as curl_requests

        monkeypatch.setattr(curl_requests.Session, "request", refuse)
        monkeypatch.setattr(curl_requests.AsyncSession, "request", refuse)
    except Exception:
        pass


def _restore_live_env():
    """Reload the repo ``.env`` into the environment on opt-in.

    The upstream conftest blanks ``TRADINGAGENTS_*`` at import time; a plain
    ``load_dotenv`` will not override those blanks. On opt-in we force the real
    values back so the live runner sees the supplied provider/model IDs.
    """
    from dotenv import dotenv_values

    values = dotenv_values(_REPO_ROOT / ".env")
    for name, value in values.items():
        if name.startswith("TRADINGAGENTS_") and value:
            os.environ[name] = value


@pytest.fixture(autouse=True)
def _live_env(request):
    """On opt-in, restore the supplied live configuration before the test body."""
    if live_enabled() and request.node.get_closest_marker("live"):
        _restore_live_env()
    yield


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
