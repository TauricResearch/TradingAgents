"""Tests for tradingagents/portfolio/config.py."""

import pytest
from tradingagents.portfolio.config import validate_config

def test_validate_config_valid():
    """Happy path: valid configuration."""
    cfg = {
        "max_positions": 10,
        "max_position_pct": 0.1,
        "max_sector_pct": 0.3,
        "min_cash_pct": 0.05,
        "default_budget": 100000.0
    }
    # Should not raise any exception
    validate_config(cfg)

def test_validate_config_max_positions_invalid():
    """max_positions must be >= 1."""
    cfg = {
        "max_positions": 0,
        "max_position_pct": 0.1,
        "max_sector_pct": 0.3,
        "min_cash_pct": 0.05,
        "default_budget": 100000.0
    }
    with pytest.raises(ValueError, match=r"max_positions must be >= 1"):
        validate_config(cfg)

    cfg["max_positions"] = -1
    with pytest.raises(ValueError, match=r"max_positions must be >= 1"):
        validate_config(cfg)

def test_validate_config_max_position_pct_invalid():
    """max_position_pct must be in (0, 1]."""
    cfg = {
        "max_positions": 10,
        "max_position_pct": 0.0,
        "max_sector_pct": 0.3,
        "min_cash_pct": 0.05,
        "default_budget": 100000.0
    }
    with pytest.raises(ValueError, match=r"max_position_pct must be in \(0, 1\]"):
        validate_config(cfg)

    cfg["max_position_pct"] = 1.1
    with pytest.raises(ValueError, match=r"max_position_pct must be in \(0, 1\]"):
        validate_config(cfg)

def test_validate_config_max_sector_pct_invalid():
    """max_sector_pct must be in (0, 1]."""
    cfg = {
        "max_positions": 10,
        "max_position_pct": 0.1,
        "max_sector_pct": 0.0,
        "min_cash_pct": 0.05,
        "default_budget": 100000.0
    }
    with pytest.raises(ValueError, match=r"max_sector_pct must be in \(0, 1\]"):
        validate_config(cfg)

    cfg["max_sector_pct"] = 1.1
    with pytest.raises(ValueError, match=r"max_sector_pct must be in \(0, 1\]"):
        validate_config(cfg)

def test_validate_config_min_cash_pct_invalid():
    """min_cash_pct must be in [0, 1)."""
    cfg = {
        "max_positions": 10,
        "max_position_pct": 0.1,
        "max_sector_pct": 0.3,
        "min_cash_pct": -0.1,
        "default_budget": 100000.0
    }
    with pytest.raises(ValueError, match=r"min_cash_pct must be in \[0, 1\)"):
        validate_config(cfg)

    cfg["min_cash_pct"] = 1.0
    with pytest.raises(ValueError, match=r"min_cash_pct must be in \[0, 1\)"):
        validate_config(cfg)

def test_validate_config_default_budget_invalid():
    """default_budget must be > 0."""
    cfg = {
        "max_positions": 10,
        "max_position_pct": 0.1,
        "max_sector_pct": 0.3,
        "min_cash_pct": 0.05,
        "default_budget": 0.0
    }
    with pytest.raises(ValueError, match=r"default_budget must be > 0"):
        validate_config(cfg)

def test_validate_config_sum_constraints_invalid():
    """min_cash_pct + max_position_pct must be <= 1.0."""
    cfg = {
        "max_positions": 10,
        "max_position_pct": 0.6,
        "max_sector_pct": 0.3,
        "min_cash_pct": 0.5,
        "default_budget": 100000.0
    }
    with pytest.raises(ValueError, match=r"must be <= 1.0"):
        validate_config(cfg)

def test_validate_config_sum_constraints_edge_case():
    """min_cash_pct + max_position_pct can be exactly 1.0."""
    cfg = {
        "max_positions": 10,
        "max_position_pct": 0.5,
        "max_sector_pct": 0.3,
        "min_cash_pct": 0.5,
        "default_budget": 100000.0
    }
    # Should not raise any exception
    validate_config(cfg)
