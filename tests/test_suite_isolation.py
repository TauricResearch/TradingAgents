"""The suite runs the same on any machine: no test reaches the network."""

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
