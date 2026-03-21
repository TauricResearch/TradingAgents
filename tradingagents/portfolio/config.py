"""Portfolio Manager configuration.

Integrates with the existing ``tradingagents/default_config.py`` pattern,
reading all portfolio settings from ``TRADINGAGENTS_<KEY>`` env vars.

All env-var reading is delegated to the shared helpers in
``tradingagents.default_config`` — that module is the single entry point
for .env loading and the ``_env*`` helper functions.

Usage::

    from tradingagents.portfolio.config import get_portfolio_config, validate_config

    cfg = get_portfolio_config()
    validate_config(cfg)
    print(cfg["max_positions"])  # 15
"""

from __future__ import annotations

import os

# Importing default_config triggers its module-level load_dotenv() calls,
# which loads the .env file (CWD first, then project root) before we read
# any TRADINGAGENTS_* variables below.  This is the single source of truth
# for .env loading — no separate load_dotenv() call needed here.
from tradingagents.default_config import _env, _env_float, _env_int


PORTFOLIO_CONFIG: dict = {
    "supabase_connection_string": os.getenv("SUPABASE_CONNECTION_STRING", ""),
    "data_dir": _env("PORTFOLIO_DATA_DIR", "reports"),
    "max_positions": 15,
    "max_position_pct": 0.15,
    "max_sector_pct": 0.35,
    "min_cash_pct": 0.05,
    "default_budget": 100_000.0,
}


def get_portfolio_config() -> dict:
    """Return the merged portfolio config (defaults overridden by env vars).

    Returns:
        A dict with all portfolio configuration keys.
    """
    cfg = dict(PORTFOLIO_CONFIG)
    cfg["supabase_connection_string"] = os.getenv("SUPABASE_CONNECTION_STRING", cfg["supabase_connection_string"])
    cfg["data_dir"] = _env("PORTFOLIO_DATA_DIR", cfg["data_dir"])
    cfg["max_positions"] = _env_int("PM_MAX_POSITIONS", cfg["max_positions"])
    cfg["max_position_pct"] = _env_float("PM_MAX_POSITION_PCT", cfg["max_position_pct"])
    cfg["max_sector_pct"] = _env_float("PM_MAX_SECTOR_PCT", cfg["max_sector_pct"])
    cfg["min_cash_pct"] = _env_float("PM_MIN_CASH_PCT", cfg["min_cash_pct"])
    cfg["default_budget"] = _env_float("PM_DEFAULT_BUDGET", cfg["default_budget"])
    return cfg


def validate_config(cfg: dict) -> None:
    """Validate a portfolio config dict, raising ValueError on invalid values.

    Args:
        cfg: Config dict as returned by ``get_portfolio_config()``.

    Raises:
        ValueError: With a descriptive message on the first failed check.
    """
    if cfg["max_positions"] < 1:
        raise ValueError(f"max_positions must be >= 1, got {cfg['max_positions']}")
    if not (0 < cfg["max_position_pct"] <= 1.0):
        raise ValueError(f"max_position_pct must be in (0, 1], got {cfg['max_position_pct']}")
    if not (0 < cfg["max_sector_pct"] <= 1.0):
        raise ValueError(f"max_sector_pct must be in (0, 1], got {cfg['max_sector_pct']}")
    if not (0 <= cfg["min_cash_pct"] < 1.0):
        raise ValueError(f"min_cash_pct must be in [0, 1), got {cfg['min_cash_pct']}")
    if cfg["default_budget"] <= 0:
        raise ValueError(f"default_budget must be > 0, got {cfg['default_budget']}")
    if cfg["min_cash_pct"] + cfg["max_position_pct"] > 1.0:
        raise ValueError(
            f"min_cash_pct ({cfg['min_cash_pct']}) + max_position_pct ({cfg['max_position_pct']}) "
            f"must be <= 1.0"
        )
