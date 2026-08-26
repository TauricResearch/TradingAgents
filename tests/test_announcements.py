"""Tests for CLI announcements fetch/display hardening."""

from unittest.mock import MagicMock, patch

import pytest

from cli import announcements as ann


@pytest.fixture(autouse=True)
def _clear_disable_env(monkeypatch):
    monkeypatch.delenv("TRADINGAGENTS_DISABLE_ANNOUNCEMENTS", raising=False)


def test_announcements_disabled_skips_network(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_DISABLE_ANNOUNCEMENTS", "1")
    with patch.object(ann.requests, "get") as get:
        result = ann.fetch_announcements()
    get.assert_not_called()
    assert result == {"announcements": [], "require_attention": False}


def test_remote_require_attention_ignored(monkeypatch):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "announcements": ["Hello [bold]world[/bold]"],
        "require_attention": True,
    }
    with patch.object(ann.requests, "get", return_value=resp):
        result = ann.fetch_announcements()
    assert result["require_attention"] is False
    assert result["trusted_fallback"] is False
    assert result["announcements"] == ["Hello [bold]world[/bold]"]


def test_display_escapes_remote_markup():
    console = MagicMock()
    ann.display_announcements(
        console,
        {
            "announcements": ["Click [link=https://evil.example]here[/link]"],
            "require_attention": False,
            "trusted_fallback": False,
        },
    )
    panel = console.print.call_args_list[0].args[0]
    # Rich escape prefixes markup brackets with backslash.
    assert panel.renderable == r"Click \[link=https://evil.example]here\[/link]"


def test_display_keeps_trusted_fallback_markup():
    console = MagicMock()
    fallback = "[cyan]ok[/cyan]"
    ann.display_announcements(
        console,
        {
            "announcements": [fallback],
            "require_attention": False,
            "trusted_fallback": True,
        },
    )
    panel = console.print.call_args_list[0].args[0]
    assert panel.renderable == fallback
