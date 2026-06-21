"""Tests for agent config."""
from __future__ import annotations

from web.server.ticker_agent.config import AgentConfig, load_config, save_config


def test_load_config_defaults(tmp_path):
    f = tmp_path / "agent_config.json"
    cfg = load_config(file_path=str(f))
    assert cfg.min_samples == 3
    assert cfg.schedule_interval_h == 1
    assert cfg.max_tickers_per_cycle == 4
    assert cfg.sp500_enabled is True
    assert cfg.yahoo_sectors_enabled is True


def test_save_and_load_roundtrip(tmp_path):
    f = tmp_path / "agent_config.json"
    cfg = AgentConfig(min_samples=5, schedule_interval_h=12)
    save_config(cfg, file_path=str(f))
    loaded = load_config(file_path=str(f))
    assert loaded.min_samples == 5
    assert loaded.schedule_interval_h == 12
