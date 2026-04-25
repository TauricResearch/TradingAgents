from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _load_run_node_live_module():
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "run_node_live.py"
    spec = importlib.util.spec_from_file_location("run_node_live_for_tests", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("raw_timeout", ["0", "-1", "inf", "nan"])
def test_run_node_live_request_timeout_rejects_invalid_values(monkeypatch, raw_timeout):
    module = _load_run_node_live_module()

    monkeypatch.setenv("TRADINGAGENTS_RUN_NODE_LIVE_REQUEST_TIMEOUT_SEC", raw_timeout)

    assert module._request_timeout() == 30.0


@pytest.mark.parametrize("raw_timeout", ["0", "-1", "inf", "nan"])
def test_ollama_tags_timeout_rejects_invalid_values(monkeypatch, raw_timeout):
    from cli import utils

    captured = {}
    response = MagicMock()
    response.json.return_value = {"models": [{"name": "qwen2.5:7b"}]}

    def _get(_url, *, timeout):
        captured["timeout"] = timeout
        return response

    monkeypatch.setenv("TRADINGAGENTS_OLLAMA_TAGS_TIMEOUT_SEC", raw_timeout)
    with patch("cli.utils.requests.get", _get):
        assert utils._fetch_ollama_models() == [("qwen2.5:7b", "qwen2.5:7b")]

    assert captured["timeout"] == 5.0
