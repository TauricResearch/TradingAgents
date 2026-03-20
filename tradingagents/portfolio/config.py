"""Portfolio Manager configuration.

Reads all portfolio-related settings from environment variables with sensible
defaults. Integrates with the existing ``tradingagents/default_config.py``
pattern.

Usage::

    from tradingagents.portfolio.config import get_portfolio_config, validate_config

    cfg = get_portfolio_config()
    validate_config(cfg)
    print(cfg["max_positions"])  # 15

Environment variables (all optional):

    SUPABASE_URL            Supabase project URL (default: "")
    SUPABASE_KEY            Supabase anon/service role key (default: "")
    PORTFOLIO_DATA_DIR      Root dir for filesystem reports (default: "reports")
    PM_MAX_POSITIONS        Max open positions (default: 15)
    PM_MAX_POSITION_PCT     Max single-position weight 0–1 (default: 0.15)
    PM_MAX_SECTOR_PCT       Max sector weight 0–1 (default: 0.35)
    PM_MIN_CASH_PCT         Minimum cash reserve 0–1 (default: 0.05)
    PM_DEFAULT_BUDGET       Default starting cash in USD (default: 100000.0)
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

PORTFOLIO_CONFIG: dict = {
    # Supabase connection
    "supabase_url": "",
    "supabase_key": "",
    # Filesystem report root (matches report_paths.py REPORTS_ROOT)
    "data_dir": "reports",
    # PM constraint defaults
    "max_positions": 15,
    "max_position_pct": 0.15,
    "max_sector_pct": 0.35,
    "min_cash_pct": 0.05,
    "default_budget": 100_000.0,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_portfolio_config() -> dict:
    """Return the merged portfolio config (defaults overridden by env vars).

    Reads ``SUPABASE_URL``, ``SUPABASE_KEY``, ``PORTFOLIO_DATA_DIR``,
    ``PM_MAX_POSITIONS``, ``PM_MAX_POSITION_PCT``, ``PM_MAX_SECTOR_PCT``,
    ``PM_MIN_CASH_PCT``, and ``PM_DEFAULT_BUDGET`` from the environment.

    Returns:
        A dict with all portfolio configuration keys.
    """
    # TODO: implement — merge PORTFOLIO_CONFIG with env var overrides
    raise NotImplementedError


def validate_config(cfg: dict) -> None:
    """Validate a portfolio config dict, raising ValueError on invalid values.

    Checks:
    - ``max_positions >= 1``
    - ``0 < max_position_pct <= 1``
    - ``0 < max_sector_pct <= 1``
    - ``0 <= min_cash_pct < 1``
    - ``default_budget > 0``
    - ``min_cash_pct + max_position_pct <= 1`` (can always meet both constraints)

    Args:
        cfg: Config dict as returned by ``get_portfolio_config()``.

    Raises:
        ValueError: With a descriptive message on the first failed check.
    """
    # TODO: implement
    raise NotImplementedError
