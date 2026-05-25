"""Unit tests for the autoload-viewer helper introduced in cli/main.py."""

import socket
import unittest
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestPortOpen(unittest.TestCase):

    def test_returns_true_when_port_is_bound(self):
        from cli.main import _port_open
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
            srv.bind(("127.0.0.1", 0))
            srv.listen(1)
            port = srv.getsockname()[1]
            self.assertTrue(_port_open(port))

    def test_returns_false_when_nothing_listening(self):
        from cli.main import _port_open
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tmp:
            tmp.bind(("127.0.0.1", 0))
            port = tmp.getsockname()[1]
        # tmp is closed; port should now be free
        self.assertFalse(_port_open(port))

    def test_returns_bool_type(self):
        from cli.main import _port_open
        with patch("cli.main.socket.create_connection", side_effect=OSError):
            result = _port_open(9999)
        self.assertIsInstance(result, bool)

    def test_connection_refused_is_false(self):
        from cli.main import _port_open
        with patch("cli.main.socket.create_connection", side_effect=ConnectionRefusedError):
            self.assertFalse(_port_open(7788))

    def test_os_error_is_false(self):
        from cli.main import _port_open
        with patch("cli.main.socket.create_connection", side_effect=OSError):
            self.assertFalse(_port_open(7788))

    def test_successful_connection_is_closed(self):
        from cli.main import _port_open
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=MagicMock())
        mock_ctx.__exit__ = MagicMock(return_value=False)
        with patch("cli.main.socket.create_connection", return_value=mock_ctx):
            result = _port_open(7788)
        self.assertTrue(result)
        mock_ctx.__exit__.assert_called_once()


if __name__ == "__main__":
    unittest.main()
