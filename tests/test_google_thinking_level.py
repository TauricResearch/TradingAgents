"""Gemini thinking_level forwarding (Gemini 3.x).

The catalog is Gemini 3.x only, which takes the string ``thinking_level``
directly. Pro, Gemini 3.8+ and the -latest aliases reject "minimal" with a 400,
so it is mapped to "low" there; numbered Flash models before 3.8 accept it.
"""

from unittest import mock

import pytest

from tradingagents.llm_clients.google_client import GoogleClient


def _captured_kwargs(model, **kwargs):
    captured = {}
    with mock.patch.object(
        __import__("tradingagents.llm_clients.google_client", fromlist=["x"]),
        "NormalizedChatGoogleGenerativeAI",
        lambda **kw: captured.setdefault("kw", kw),
    ):
        GoogleClient(model, api_key="x", **kwargs).get_llm()
    return captured["kw"]


@pytest.mark.parametrize("level", ["minimal", "low", "medium", "high"])
def test_flash_passes_thinking_level_through(level):
    kw = _captured_kwargs("gemini-3.5-flash", thinking_level=level)
    assert kw["thinking_level"] == level
    assert "thinking_budget" not in kw  # the 2.5-era param is gone


def test_pro_remaps_minimal_to_low():
    kw = _captured_kwargs("gemini-3.1-pro-preview", thinking_level="minimal")
    assert kw["thinking_level"] == "low"  # Pro doesn't accept "minimal"


def test_flash_38_remaps_minimal_to_low():
    kw = _captured_kwargs("gemini-3.8-flash", thinking_level="minimal")
    assert kw["thinking_level"] == "low"  # 3.8 Flash 400s on "minimal"


def test_flash_38_keeps_supported_levels():
    kw = _captured_kwargs("gemini-3.8-flash", thinking_level="high")
    assert kw["thinking_level"] == "high"


@pytest.mark.parametrize("alias", ["gemini-flash-latest", "gemini-pro-latest"])
def test_latest_alias_remaps_minimal_to_low(alias):
    # Aliases move between generations; gemini-flash-latest 400s on "minimal".
    assert _captured_kwargs(alias, thinking_level="minimal")["thinking_level"] == "low"


def test_pro_keeps_high():
    kw = _captured_kwargs("gemini-3.1-pro-preview", thinking_level="high")
    assert kw["thinking_level"] == "high"


def test_no_thinking_level_is_omitted():
    kw = _captured_kwargs("gemini-3.5-flash")
    assert "thinking_level" not in kw
    assert "thinking_budget" not in kw
