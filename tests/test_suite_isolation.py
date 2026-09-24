"""The suite runs the same on any machine: no test reaches the network or the user's files."""

import socket

import pytest


@pytest.mark.unit
@pytest.mark.parametrize("connect", [
    lambda: socket.create_connection(("192.0.2.1", 80), timeout=1),
    lambda: socket.socket().connect_ex(("192.0.2.1", 80)),
], ids=["connect", "connect_ex"])
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
