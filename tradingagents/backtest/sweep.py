"""Light grid-search runner around the parameters most likely to matter.

**Reminder: this exercises real LLM endpoints — running a sweep costs
money.** The harness exists so you can run it intentionally, not by
accident. CI does not invoke it.

Usage::

    from tradingagents.backtest.data_collector import list_fixtures, load_contract
    from tradingagents.backtest.sweep import run_sweep

    contracts = [load_contract(name) for name in list_fixtures()]
    results = run_sweep(
        contracts=contracts,
        grid={
            "kelly_multiplier_override": [0.10, 0.25, 0.50],
            "max_debate_rounds": [1, 2],
        },
    )
    print(results)

The result is a pandas DataFrame keyed by parameter combo, with the
:func:`tradingagents.backtest.metrics.summary` columns plus a Pareto
flag (``hit_rate``, ``total_pnl_usd``, ``kelly_growth_rate``) so you can
filter to the frontier.
"""

from __future__ import annotations

import itertools
import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from tradingagents.backtest import metrics, replay
from tradingagents.backtest.data_collector import HistoricalContract
from tradingagents.default_config import DEFAULT_CONFIG

logger = logging.getLogger(__name__)


def _expand_grid(grid: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
    """Cartesian product of the grid axes, each combo as a dict."""
    if not grid:
        return [{}]
    keys = list(grid.keys())
    values = [grid[k] for k in keys]
    combos = []
    for vs in itertools.product(*values):
        combos.append(dict(zip(keys, vs)))
    return combos


def _config_for(combo: Dict[str, Any]) -> Dict[str, Any]:
    """Build a TradingAgents config dict by overlaying the combo on DEFAULT_CONFIG."""
    config = dict(DEFAULT_CONFIG)
    config["kalshi"] = dict(DEFAULT_CONFIG.get("kalshi", {}))

    for key, value in combo.items():
        if key in {"max_debate_rounds", "max_risk_discuss_rounds"}:
            config[key] = value
        elif key in {"deep_think_llm", "quick_think_llm", "llm_provider"}:
            config[key] = value
        elif key == "kelly_multiplier_override":
            # Sizing module reads this off the config when present.
            config["kalshi"]["kelly_multiplier"] = value
        else:
            config[key] = value
    return config


def run_sweep(
    *,
    contracts: List[HistoricalContract],
    grid: Optional[Dict[str, List[Any]]] = None,
) -> pd.DataFrame:
    """Run the agent pipeline across each (contract, param-combo) pair.

    Returns a DataFrame with one row per param combo, summarizing the
    performance metrics across all replayed contracts.
    """
    grid = grid or {}
    combos = _expand_grid(grid)

    rows: List[Dict[str, Any]] = []
    for combo in combos:
        config = _config_for(combo)
        records = []
        for contract in contracts:
            try:
                result = replay.replay_contract(contract, config=config)
                records.append(replay.to_record(contract, result))
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "Replay failed for %s under combo %s", contract.contract_id, combo
                )
                continue
        if not records:
            continue
        df = metrics.to_df(records)
        s = metrics.summary(df)
        rows.append({**combo, **s})

    return pd.DataFrame(rows)


def pareto_mask(sweep_df: pd.DataFrame, *, columns=("hit_rate", "total_pnl_usd")) -> pd.Series:
    """Boolean mask of Pareto-optimal rows on the given metric columns."""
    if sweep_df.empty:
        return pd.Series(dtype=bool)

    rows = sweep_df[list(columns)].to_numpy()
    keep = []
    for i, row in enumerate(rows):
        dominated = False
        for j, other in enumerate(rows):
            if i == j:
                continue
            if all(other >= row) and any(other > row):
                dominated = True
                break
        keep.append(not dominated)
    return pd.Series(keep, index=sweep_df.index)
