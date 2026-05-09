"""Unit tests for cli/utils.py — non-interactive / MLX helper functions.

Covers:
- parse_research_depth_flag
- parse_analysts_flag
- validate_analysis_date_cli
- default_backend_url_for_provider
- verify_mlx_server_reachable  (mocked socket + requests)
- warn_mlx_quick_deep_mismatch
- _scan_hf_cache_mlx_models
"""

import os
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# parse_research_depth_flag
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestParseResearchDepthFlag(unittest.TestCase):

    def _parse(self, value):
        from cli.utils import parse_research_depth_flag
        return parse_research_depth_flag(value)

    def test_shallow_returns_1(self):
        self.assertEqual(self._parse("shallow"), 1)

    def test_medium_returns_3(self):
        self.assertEqual(self._parse("medium"), 3)

    def test_deep_returns_5(self):
        self.assertEqual(self._parse("deep"), 5)

    def test_numeric_1(self):
        self.assertEqual(self._parse("1"), 1)

    def test_numeric_3(self):
        self.assertEqual(self._parse("3"), 3)

    def test_numeric_5(self):
        self.assertEqual(self._parse("5"), 5)

    def test_case_insensitive(self):
        self.assertEqual(self._parse("SHALLOW"), 1)
        self.assertEqual(self._parse("Medium"), 3)

    def test_whitespace_stripped(self):
        self.assertEqual(self._parse("  deep  "), 5)

    def test_invalid_raises_value_error(self):
        with self.assertRaises(ValueError):
            self._parse("extreme")

    def test_invalid_number_raises_value_error(self):
        with self.assertRaises(ValueError):
            self._parse("2")


# ---------------------------------------------------------------------------
# parse_analysts_flag
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestParseAnalystsFlag(unittest.TestCase):

    def _parse(self, value):
        from cli.utils import parse_analysts_flag
        return parse_analysts_flag(value)

    def test_single_analyst(self):
        from cli.models import AnalystType
        result = self._parse("market")
        self.assertEqual(result, [AnalystType.MARKET])

    def test_all_four_analysts(self):
        from cli.models import AnalystType
        result = self._parse("market,social,news,fundamentals")
        self.assertEqual(len(result), 4)
        self.assertIn(AnalystType.MARKET, result)
        self.assertIn(AnalystType.FUNDAMENTALS, result)

    def test_whitespace_around_commas(self):
        from cli.models import AnalystType
        result = self._parse(" market , news ")
        self.assertIn(AnalystType.MARKET, result)
        self.assertIn(AnalystType.NEWS, result)

    def test_case_insensitive(self):
        from cli.models import AnalystType
        result = self._parse("MARKET")
        self.assertEqual(result, [AnalystType.MARKET])

    def test_empty_raises_value_error(self):
        with self.assertRaises(ValueError):
            self._parse("")

    def test_unknown_analyst_raises_value_error(self):
        with self.assertRaises(ValueError):
            self._parse("technical")

    def test_duplicates_allowed(self):
        result = self._parse("market,market")
        self.assertEqual(len(result), 2)


# ---------------------------------------------------------------------------
# validate_analysis_date_cli
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestValidateAnalysisDateCli(unittest.TestCase):

    def _validate(self, value):
        from cli.utils import validate_analysis_date_cli
        return validate_analysis_date_cli(value)

    def test_valid_past_date(self):
        result = self._validate("2025-01-15")
        self.assertEqual(result, "2025-01-15")

    def test_strips_whitespace(self):
        result = self._validate("  2024-06-01  ")
        self.assertEqual(result, "2024-06-01")

    def test_future_date_raises(self):
        future = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")
        with self.assertRaises(ValueError):
            self._validate(future)

    def test_bad_format_raises(self):
        with self.assertRaises(ValueError):
            self._validate("01/15/2025")

    def test_invalid_calendar_date_raises(self):
        with self.assertRaises(ValueError):
            self._validate("2025-02-30")

    def test_today_is_accepted(self):
        today = datetime.now().strftime("%Y-%m-%d")
        result = self._validate(today)
        self.assertEqual(result, today)


# ---------------------------------------------------------------------------
# default_backend_url_for_provider
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestDefaultBackendUrl(unittest.TestCase):

    def test_mlx_returns_localhost_8000(self):
        from cli.utils import default_backend_url_for_provider
        url = default_backend_url_for_provider("mlx")
        self.assertIn("localhost:8000", url)

    def test_ollama_returns_localhost_11434(self):
        from cli.utils import default_backend_url_for_provider
        url = default_backend_url_for_provider("ollama")
        self.assertIn("11434", url)

    def test_google_returns_none(self):
        from cli.utils import default_backend_url_for_provider
        self.assertIsNone(default_backend_url_for_provider("google"))

    def test_unknown_provider_returns_none(self):
        from cli.utils import default_backend_url_for_provider
        self.assertIsNone(default_backend_url_for_provider("unknown_provider_xyz"))

    def test_case_insensitive(self):
        from cli.utils import default_backend_url_for_provider
        self.assertEqual(
            default_backend_url_for_provider("MLX"),
            default_backend_url_for_provider("mlx"),
        )


# ---------------------------------------------------------------------------
# verify_mlx_server_reachable
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestVerifyMlxServerReachable(unittest.TestCase):

    def _call(self, url="http://localhost:8000/v1"):
        from cli.utils import verify_mlx_server_reachable
        return verify_mlx_server_reachable(url)

    def test_connection_refused_calls_exit(self):
        import socket
        with patch("socket.create_connection", side_effect=OSError("refused")):
            with self.assertRaises(SystemExit):
                self._call()

    def test_http_401_calls_exit(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {"error": {"message": "Unauthorized"}}
        mock_resp.headers = {"server": "oMLX/1.0"}

        fake_requests = MagicMock()
        fake_requests.get.return_value = mock_resp
        fake_requests.RequestException = Exception

        with patch("socket.create_connection"):
            with patch.dict("sys.modules", {"requests": fake_requests}):
                with self.assertRaises(SystemExit):
                    self._call()

    def test_http_200_does_not_exit(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        fake_requests = MagicMock()
        fake_requests.get.return_value = mock_resp
        fake_requests.RequestException = Exception

        with patch("socket.create_connection"):
            with patch.dict("sys.modules", {"requests": fake_requests}):
                self._call()  # should not raise

    def test_request_exception_does_not_exit(self):
        """Non-auth network errors are deferred to the agent run."""
        fake_requests = MagicMock()
        fake_requests.get.side_effect = Exception("timeout")
        fake_requests.RequestException = Exception

        with patch("socket.create_connection"):
            with patch.dict("sys.modules", {"requests": fake_requests}):
                self._call()  # should not raise

    def test_none_url_uses_default_port(self):
        """None backend_url should fall back to localhost:8000 (not raise)."""
        import socket as _socket
        calls = []

        def record_connect(address, timeout=None):
            calls.append(address)
            raise OSError("refused")

        with patch("socket.create_connection", side_effect=record_connect):
            with self.assertRaises(SystemExit):
                self._call(url=None)

        self.assertTrue(calls, "socket.create_connection was never called")
        host, port = calls[0]
        self.assertEqual(host, "localhost")
        self.assertEqual(port, 8000)


# ---------------------------------------------------------------------------
# warn_mlx_quick_deep_mismatch
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestWarnMlxQuickDeepMismatch(unittest.TestCase):

    def test_same_model_prints_nothing(self):
        from cli.utils import warn_mlx_quick_deep_mismatch

        with patch("cli.utils.console") as mock_console:
            warn_mlx_quick_deep_mismatch("model-a", "model-a")
            mock_console.print.assert_not_called()

    def test_different_models_prints_panel(self):
        from cli.utils import warn_mlx_quick_deep_mismatch

        with patch("cli.utils.console") as mock_console:
            warn_mlx_quick_deep_mismatch("model-a", "model-b")
            mock_console.print.assert_called_once()


# ---------------------------------------------------------------------------
# _scan_hf_cache_mlx_models
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestScanHfCacheMlxModels(unittest.TestCase):

    def test_missing_cache_returns_empty(self):
        from cli.utils import _scan_hf_cache_mlx_models

        with patch("cli.utils._hf_cache_dir", return_value=Path("/nonexistent/path/xyz")):
            result = _scan_hf_cache_mlx_models()

        self.assertEqual(result, [])

    def test_finds_mlx_community_models(self, tmp_path=None):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            # mlx-community org — should be found
            (cache / "models--mlx-community--Qwen2.5-7B-4bit").mkdir()
            # unknown org — should NOT be found
            (cache / "models--someorg--SomeModel").mkdir()
            # non-model entry — should be skipped
            (cache / "datasets--foo--bar").mkdir()

            from cli.utils import _scan_hf_cache_mlx_models

            with patch("cli.utils._hf_cache_dir", return_value=cache):
                result = _scan_hf_cache_mlx_models()

        self.assertIn("mlx-community/Qwen2.5-7B-4bit", result)
        self.assertNotIn("someorg/SomeModel", result)

    def test_finds_models_with_mlx_hint_in_name(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            # org not in _MLX_HF_ORGS but name contains "-4bit" hint
            (cache / "models--myorg--MyModel-4bit").mkdir()

            from cli.utils import _scan_hf_cache_mlx_models

            with patch("cli.utils._hf_cache_dir", return_value=cache):
                result = _scan_hf_cache_mlx_models()

        self.assertIn("myorg/MyModel-4bit", result)

    def test_result_is_sorted(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            (cache / "models--mlx-community--Z-model-4bit").mkdir()
            (cache / "models--mlx-community--A-model-4bit").mkdir()

            from cli.utils import _scan_hf_cache_mlx_models

            with patch("cli.utils._hf_cache_dir", return_value=cache):
                result = _scan_hf_cache_mlx_models()

        self.assertEqual(result, sorted(result))

    def test_hf_home_env_var_honoured(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            hf_home = Path(tmp)
            hub = hf_home / "hub"
            hub.mkdir()
            (hub / "models--mlx-community--TestModel-4bit").mkdir()

            from cli.utils import _hf_cache_dir

            with patch.dict(os.environ, {"HF_HOME": str(hf_home)}, clear=False):
                # Unset HF_HUB_CACHE so HF_HOME takes effect
                env = {k: v for k, v in os.environ.items() if k != "HF_HUB_CACHE"}
                with patch.dict(os.environ, env, clear=True):
                    result = _hf_cache_dir()

            self.assertEqual(result, hub)
