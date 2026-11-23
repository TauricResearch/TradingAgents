"""The platform's configuration: the TradingAgents defaults, Anthropic models unless told otherwise.

``DEFAULT_CONFIG`` already applies every ``TRADINGAGENTS_*`` variable from the
environment and ``.env``. The platform only changes what was left unset: when no
provider is named there, it uses Anthropic, so a ``.env`` holding just
``ANTHROPIC_API_KEY`` is enough to run.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path

from tradingagents.default_config import DEFAULT_CONFIG

DEFAULT_PROVIDER = "anthropic"
DEFAULT_DEEP_MODEL = "claude-opus-5-5"      # research manager and portfolio manager
DEFAULT_QUICK_MODEL = "claude-sonnet-5-5"   # analysts, researchers, debaters, trader

# The paper portfolio's defaults; every one can be changed per simulation.
PAPER_DEFAULTS = {
    "starting_cash": 100_000.0,
    "commission_bps": 5.0,        # per side, on traded value
    "slippage_bps": 5.0,          # per side, on traded value
    "overweight_scale": 0.5,      # an Overweight takes this share of the full Buy size
    "underweight_scale": 0.5,     # an Underweight keeps this share of the current position
    "use_stops": True,            # exit at the close that ends below the recorded ATR stop
    "fallback_size_pct": 0.05,    # used only when a run recorded no risk-based size
}

# Forward windows, in trading days, the scorecard measures each signal over.
SCORE_HORIZONS = (5, 21, 63)

ANALYSTS = ("market", "social", "news", "fundamentals", "valuation")


def platform_config(overrides: dict | None = None) -> dict:
    """A fresh config for platform runs: the repo defaults plus Anthropic where unset."""
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if not os.getenv("TRADINGAGENTS_LLM_PROVIDER"):
        cfg["llm_provider"] = DEFAULT_PROVIDER
        if not os.getenv("TRADINGAGENTS_DEEP_THINK_LLM"):
            cfg["deep_think_llm"] = DEFAULT_DEEP_MODEL
        if not os.getenv("TRADINGAGENTS_QUICK_THINK_LLM"):
            cfg["quick_think_llm"] = DEFAULT_QUICK_MODEL
    if overrides:
        cfg.update(overrides)
    return cfg


def platform_dir(cfg: dict) -> Path:
    """Where the platform keeps its database: beside the run results."""
    path = Path(cfg["results_dir"]).expanduser() / "platform"
    path.mkdir(parents=True, exist_ok=True)
    return path


def provider_key_status(cfg: dict) -> tuple[str, bool]:
    """(the key variable the chosen provider reads, whether it is set) — never the value."""
    names = {
        "anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "google": "GOOGLE_API_KEY",
        "xai": "XAI_API_KEY", "deepseek": "DEEPSEEK_API_KEY", "openrouter": "OPENROUTER_API_KEY",
        "mistral": "MISTRAL_API_KEY", "groq": "GROQ_API_KEY",
    }
    name = names.get(str(cfg.get("llm_provider", "")).lower(), "")
    return name, bool(name and os.getenv(name, "").strip())
