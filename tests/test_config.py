"""Tests for the global configuration (defaults + TOML overlay)."""

from __future__ import annotations

import pytest

from tradingagents.config import Settings, load_settings

pytestmark = pytest.mark.unit


def test_defaults_when_no_file(tmp_path):
    s = load_settings(tmp_path / "nope.toml")
    assert s.llm.provider == "openrouter"
    assert s.risk.base_risk_pct == 0.01
    assert s.charter.max_sector_pct == 0.30
    assert s.cycle.max_revisions == 1
    # universe / watchlist / benchmark defaults
    assert s.universe.scope == "watchlist"
    assert s.watchlist.membership == "hybrid" and s.watchlist.seed == "sp500"
    assert s.benchmark.symbols == ["SPY"]
    assert s.cycle.max_parallel == 3


def test_toml_overlay_is_partial(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        """
[risk]
base_risk_pct = 0.02
k_stop = 3.0

[charter]
max_sector_pct = 0.25

[llm]
deep_model = "openrouter/owl-alpha"

[benchmark]
symbols = ["SPY", "QQQ"]

[watchlist]
max_size = 100
""".strip()
    )
    s = load_settings(p)
    # overridden
    assert s.risk.base_risk_pct == 0.02
    assert s.risk.k_stop == 3.0
    assert s.charter.max_sector_pct == 0.25
    assert s.llm.deep_model == "openrouter/owl-alpha"
    assert s.benchmark.symbols == ["SPY", "QQQ"]
    assert s.watchlist.max_size == 100
    # untouched keep defaults
    assert s.risk.k_tp == 3.0
    assert s.risk.max_position_pct == 0.10
    assert s.llm.quick_model == "openrouter/owl-alpha"


def test_convenience_views():
    s = Settings()
    assert s.llm_config()["llm_provider"] == "openrouter"
    cd = s.charter_dict()
    assert cd["max_sector_pct"] == 0.30 and cd["min_risk_reward"] == 1.5
    assert cd["base_risk_pct"] == 0.01
