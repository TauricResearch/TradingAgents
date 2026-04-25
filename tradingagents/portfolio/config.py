"""Portfolio Manager configuration.

Integrates with the shared ``tradingagents/default_config.py`` env helpers,
reading portfolio settings from ``TRADINGAGENTS_<KEY>`` env vars.

All ``TRADINGAGENTS_*`` reads are delegated to shared helpers in
``tradingagents.default_config``.

Usage::

    from tradingagents.portfolio.config import get_portfolio_config, validate_config

    cfg = get_portfolio_config()
    validate_config(cfg)
    print(cfg["max_positions"])  # 15
"""

from __future__ import annotations

from tradingagents.default_config import _env, _env_float, _env_int, get_env_value
from tradingagents.portfolio.types import PortfolioConfig

PORTFOLIO_CONFIG: PortfolioConfig = {
    "supabase_connection_string": get_env_value("SUPABASE_CONNECTION_STRING", ""),
    # PORTFOLIO_DATA_DIR takes precedence; falls back to TRADINGAGENTS_REPORTS_DIR,
    # then to "reports" (relative to CWD) — same default as report_paths.REPORTS_ROOT.
    "data_dir": get_env_value("PORTFOLIO_DATA_DIR") or _env("REPORTS_DIR", "reports"),
    "mongo_uri": get_env_value("MONGO_URI", ""),
    "mongo_db": get_env_value("MONGO_DB", "tradingagents"),
    "max_positions": 15,
    "max_position_pct": 0.15,
    "max_sector_pct": 0.35,
    "min_cash_pct": 0.05,
    "default_budget": 100_000.0,
    "results_dir": _env("REPORTS_DIR", "reports"),
}


def get_portfolio_config() -> PortfolioConfig:
    """Return the merged portfolio config (defaults overridden by env vars).

    Returns:
        A PortfolioConfig dict with all portfolio configuration keys.
    """
    cfg: PortfolioConfig = dict(PORTFOLIO_CONFIG)  # type: ignore
    cfg["supabase_connection_string"] = get_env_value(
        "SUPABASE_CONNECTION_STRING", cfg.get("supabase_connection_string", "")
    )
    cfg["data_dir"] = get_env_value("PORTFOLIO_DATA_DIR") or _env(
        "REPORTS_DIR", cfg.get("data_dir", "reports")
    )
    cfg["mongo_uri"] = get_env_value("MONGO_URI", cfg.get("mongo_uri", ""))
    cfg["mongo_db"] = get_env_value("MONGO_DB", cfg.get("mongo_db", "tradingagents"))
    cfg["results_dir"] = _env("REPORTS_DIR", cfg.get("results_dir", "reports"))
    cfg["max_positions"] = _env_int("PM_MAX_POSITIONS", cfg.get("max_positions", 15))
    cfg["max_position_pct"] = _env_float("PM_MAX_POSITION_PCT", cfg.get("max_position_pct", 0.15))
    cfg["max_sector_pct"] = _env_float("PM_MAX_SECTOR_PCT", cfg.get("max_sector_pct", 0.35))
    cfg["min_cash_pct"] = _env_float("PM_MIN_CASH_PCT", cfg.get("min_cash_pct", 0.05))
    cfg["default_budget"] = _env_float("PM_DEFAULT_BUDGET", cfg.get("default_budget", 100_000.0))
    return cfg


def validate_config(cfg: PortfolioConfig) -> None:
    """Validate a portfolio config dict, raising ValueError on invalid values.

    Args:
        cfg: PortfolioConfig dict as returned by ``get_portfolio_config()``.

    Raises:
        ValueError: With a descriptive message on the first failed check.
    """
    max_pos = cfg.get("max_positions", 15)
    if max_pos < 1:
        raise ValueError(f"max_positions must be >= 1, got {max_pos}")
    max_pct = cfg.get("max_position_pct", 0.15)
    if not (0 < max_pct <= 1.0):
        raise ValueError(f"max_position_pct must be in (0, 1], got {max_pct}")
    max_sector = cfg.get("max_sector_pct", 0.35)
    if not (0 < max_sector <= 1.0):
        raise ValueError(f"max_sector_pct must be in (0, 1], got {max_sector}")
    min_cash = cfg.get("min_cash_pct", 0.05)
    if not (0 <= min_cash < 1.0):
        raise ValueError(f"min_cash_pct must be in [0, 1), got {min_cash}")
    budget = cfg.get("default_budget", 100_000.0)
    if budget <= 0:
        raise ValueError(f"default_budget must be > 0, got {budget}")
    if min_cash + max_pct > 1.0:
        raise ValueError(f"min_cash_pct ({min_cash}) + max_position_pct ({max_pct}) must be <= 1.0")
