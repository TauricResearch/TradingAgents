"""The suite runs the same on any machine: no test reaches the network or the user's files."""

import socket

import pytest


@pytest.mark.unit
@pytest.mark.parametrize("connect", [
    lambda: socket.create_connection(("192.0.2.1", 80), timeout=1),
    lambda: socket.socket().connect_ex(("192.0.2.1", 80)),
    lambda: socket.getaddrinfo("example.com", 443),
    # yfinance's HTTP client is libcurl, which never touches Python's sockets.
    lambda: __import__("curl_cffi.requests").requests.Session().get("http://192.0.2.1", timeout=1),
], ids=["connect", "connect_ex", "dns", "curl_cffi"])
def test_a_test_cannot_reach_the_network(connect):
    """A test that silently depends on a live vendor passes or fails with the
    machine it runs on; conftest refuses the connection instead."""
    with pytest.raises(OSError, match="reach the network"):
        connect()


@pytest.mark.unit
def test_a_test_saves_cli_selections_to_its_own_directory(tmp_path):
    """The CLI remembers the last run's selections in the user's home; a test
    that runs the selection flow would otherwise overwrite them."""
    from cli import prefs

    prefs.save_last_run({"analysts": ["market"]})

    assert prefs._PREFS_PATH.is_relative_to(tmp_path)
    assert prefs._PREFS_PATH.exists()


@pytest.mark.unit
def test_yfinance_keeps_its_cache_out_of_the_users_home():
    """yfinance caches each symbol's time zone on disk, in the home directory by default."""
    import tempfile
    from pathlib import Path

    from yfinance.cache import _TzDBManager

    location = Path(_TzDBManager.get_location())
    assert location.is_relative_to(Path(tempfile.gettempdir()))
    assert location.name.startswith("tradingagents-tests-yf-")


@pytest.mark.unit
@pytest.mark.parametrize("key", ["results_dir", "data_cache_dir", "memory_log_path"])
def test_the_suite_keeps_its_files_out_of_the_users_home(key):
    """A test that reads the user's cache sees what their runs fetched, and passes
    or fails with it; one that writes there changes their data."""
    from pathlib import Path

    from tradingagents.default_config import DEFAULT_CONFIG

    assert not Path(DEFAULT_CONFIG[key]).is_relative_to(Path.home() / ".tradingagents")
