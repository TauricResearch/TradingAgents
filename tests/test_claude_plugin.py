"""The Claude Code plugin bundles the MCP server and its research skill."""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "tradingagents"


@pytest.mark.unit
def test_marketplace_lists_the_plugin():
    marketplace = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    entries = {plugin["name"]: plugin for plugin in marketplace["plugins"]}

    assert marketplace["name"] == "tradingagents"
    assert entries["tradingagents"]["source"] == "./plugins/tradingagents"


@pytest.mark.unit
def test_plugin_bundles_the_mcp_server():
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    mcp = json.loads((PLUGIN / ".mcp.json").read_text())
    server = mcp["mcpServers"]["tradingagents"]
    launcher = PLUGIN / "bin" / "tradingagents-mcp"

    assert manifest["name"] == "tradingagents"
    assert server["command"] == "sh"
    assert "${CLAUDE_PLUGIN_ROOT}/bin/tradingagents-mcp" in server["args"]
    assert launcher.is_file()
    assert launcher.stat().st_mode & 0o111


@pytest.mark.unit
def test_plugin_skill_explains_the_no_key_mode():
    skill = (PLUGIN / "skills" / "research" / "SKILL.md").read_text()

    assert "analysis_ready" in skill
    assert "Claude-driven research" in skill
    assert "cannot reuse Claude Code's subscription" in skill
