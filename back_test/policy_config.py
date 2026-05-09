"""PortfolioState policy configuration.

Holds the dataclass + CLI argparse glue for the deterministic policy used
by the backtest-only portfolio_state_manager. Kept separate from the agent
implementation so the agent module stays focused on decisions, not on how
to be CLI-configured.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Optional


_DEFAULT_VOLUME_MULTIPLIER = {
    "expanding": 1.0,
    "normal": 1.0,
    "soft": 0.7,
    "shrinking": 0.5,
    "unavailable": 0.5,
}

# Phase modifiers — applied AFTER regime ceil/floor and volume multiplier.
# Encodes the four operating principles:
#   - 核心持仓: high floor in healthy_bull_trend / bull_pullback
#   - 不要频繁止盈: low tp_size in trend phases (15-20 vs default 25-40)
#   - 允许 trend following: market entry permitted in trend phases
#   - pullback 买入: bull_pullback gets aggressive add + at-current entry
# Keys not in dict default to no modification.
_DEFAULT_PHASE_MODIFIER: dict[str, dict] = {
    # ----- Bull -----
    "early_bull_reversal":    {"cap": 0.40, "tp_size": 30.0, "allow_add": False, "trend_market_entry": True},
    "healthy_bull_trend":     {"floor": 0.50, "cap": 0.85, "tp_size": 15.0, "allow_add": True,  "trend_market_entry": True},
    "accelerating_bull":      {"floor": 0.40, "cap": 0.80, "tp_size": 20.0, "allow_add": False, "trend_market_entry": True},
    # overextended_bull: keep core, allow trimmed add. NOT block_new_position —
    # in long bull markets "approaching resistance" is the norm, not a reason to exit.
    "overextended_bull":      {"cap": 0.55, "tp_size": 30.0, "allow_add": True},
    "bull_pullback":          {"floor": 0.50, "cap": 0.85, "tp_size": 15.0, "allow_add": True,  "pullback_buy": True},
    "late_bull_distribution": {"cap": 0.25, "tp_size": 50.0, "allow_add": False},
    # ----- Bear (force SELL existing, block new) -----
    "early_bear_reversal":    {"force_sell_if_position": True, "block_new_position": True},
    "healthy_bear_trend":     {"force_sell_if_position": True, "block_new_position": True},
    "accelerating_bear":      {"force_sell_if_position": True, "block_new_position": True},
    "oversold_bear":          {"cap": 0.0, "block_new_position": True},
    "bear_rally":             {"cap": 0.0, "block_new_position": True},      # trap for trend-followers
    "late_bear_exhaustion":   {"cap": 0.20, "tp_size": 30.0},
    # ----- Neutral -----
    "range_compression":      {"cap": 0.25, "tp_size": 60.0},                 # full TP near range top
    "high_volatility_range":  {"cap": 0.15, "block_new_position": True},
    "macro_event_regime":     {"cap": 0.10, "block_new_position": True},
    "unclear":                {"cap": 0.20},
}


@dataclass(frozen=True)
class PortfolioStatePolicyConfig:
    """Tunable deterministic policy parameters for backtest PortfolioState mode."""

    trend_score_weight: float = 0.25
    momentum_score_weight: float = 0.125
    event_score_weight: float = 0.075
    risk_score_weight: float = 0.40

    strong_uptrend_floor: float = 0.60
    strong_uptrend_cap: float = 0.90
    weak_uptrend_floor: float = 0.25
    weak_uptrend_cap: float = 0.55
    range_cap: float = 0.45
    event_driven_cap: float = 0.50
    unavailable_volume_cap: float = 0.35
    max_target_weight: float = 0.90
    min_trade_weight: float = 0.02
    order_size_multiplier: float = 1.0

    volume_multipliers: dict[str, float] = field(
        default_factory=lambda: {
            "expanding": 1.0,
            "normal": 1.0,
            "soft": 0.7,
            "shrinking": 0.5,
            "unavailable": 0.5,
        }
    )
    phase_modifiers: dict[str, dict[str, Any]] = field(default_factory=dict)

    recent_phase_lookback: int = 3
    hysteresis_confirmation_count: int = 0
    overextended_sma20_atr_threshold: float = 2.0

    pullback_entry_add_max_pct: float = 25.0
    pullback_entry_add_weight_multiplier: float = 60.0
    default_add_max_pct: float = 25.0
    default_add_weight_multiplier: float = 50.0
    weak_uptrend_soft_volume_add_max_pct: float = 15.0

    bearish_divergence_reduce_pct: float = 30.0
    bearish_divergence_stop_atr: float = 1.5
    bearish_divergence_fallback_stop_atr: float = 2.0
    stop_loss_atr_multiple: float = 1.8
    trend_take_profit_atr_multiple: float = 1.8
    trend_take_profit_recent_high_multiplier: float = 1.01
    default_take_profit_atr_multiple: float = 1.3
    strong_uptrend_take_profit_size_pct: float = 25.0
    default_take_profit_size_pct: float = 40.0
    market_context_enabled: bool = True
    market_context_ticker: str = "^GSPC"

    def merged_phase_modifiers(self) -> dict[str, dict[str, Any]]:
        merged = {phase: values.copy() for phase, values in _DEFAULT_PHASE_MODIFIER.items()}
        for phase, values in self.phase_modifiers.items():
            base = merged.setdefault(phase, {})
            base.update(values)
        return merged


def default_portfolio_state_policy_config() -> dict[str, Any]:
    """Return a serializable default config for TradingAgentsGraph config dicts."""
    return asdict(PortfolioStatePolicyConfig())


_PROFILE_PRESETS: dict[str, dict[str, Any]] = {
    "conservative": {
        "trend_score_weight": 0.18,
        "momentum_score_weight": 0.09,
        "event_score_weight": 0.05,
        "risk_score_weight": 0.55,
        "strong_uptrend_floor": 0.45,
        "strong_uptrend_cap": 0.70,
        "weak_uptrend_floor": 0.10,
        "weak_uptrend_cap": 0.30,
        "range_cap": 0.20,
        "event_driven_cap": 0.30,
        "max_target_weight": 0.70,
        "bearish_divergence_reduce_pct": 50.0,
    },
    "balanced": {},
    "aggressive": {
        "trend_score_weight": 0.35,
        "momentum_score_weight": 0.20,
        "event_score_weight": 0.10,
        "risk_score_weight": 0.30,
        "strong_uptrend_floor": 0.70,
        "strong_uptrend_cap": 1.00,
        "weak_uptrend_floor": 0.30,
        "weak_uptrend_cap": 0.60,
        "range_cap": 0.45,
        "event_driven_cap": 0.65,
        "max_target_weight": 1.00,
        "bearish_divergence_reduce_pct": 25.0,
    },
}


_TRADE_FREQUENCY_PRESETS: dict[str, dict[str, Any]] = {
    "low": {
        "min_trade_weight": 0.08,
        "hysteresis_confirmation_count": 2,
        "stop_loss_atr_multiple": 3.0,
        "trend_take_profit_atr_multiple": 4.0,
        "default_take_profit_atr_multiple": 2.5,
        "trend_take_profit_recent_high_multiplier": 1.06,
        "default_add_max_pct": 10.0,
        "pullback_entry_add_max_pct": 15.0,
        "weak_uptrend_soft_volume_add_max_pct": 5.0,
    },
    "normal": {},
    "high": {
        "min_trade_weight": 0.01,
        "hysteresis_confirmation_count": 0,
        "stop_loss_atr_multiple": 1.5,
        "trend_take_profit_atr_multiple": 1.4,
        "default_take_profit_atr_multiple": 1.1,
        "trend_take_profit_recent_high_multiplier": 1.005,
        "default_add_max_pct": 30.0,
        "pullback_entry_add_max_pct": 40.0,
        "weak_uptrend_soft_volume_add_max_pct": 20.0,
    },
}


_INDEX_STRENGTH_PRESETS: dict[str, dict[str, Any]] = {
    "off": {"market_context_enabled": False},
    "soft": {"market_context_enabled": True},
    "normal": {"market_context_enabled": True},
    "hard": {"market_context_enabled": True},
}


def add_portfolio_state_policy_args(parser) -> None:
    """Attach PortfolioStatePolicyConfig argparse options to a parser."""
    group = parser.add_argument_group("组合状态策略参数")
    group.add_argument("--ps-trade-frequency", choices=sorted(_TRADE_FREQUENCY_PRESETS), default="normal",
        help="交易频率档位：low 更少交易，normal 默认，high 更容易进出。默认 normal。")
    group.add_argument("--ps-index-context", default="^GSPC",
        dest="ps_market_context_ticker", help="指数上下文 ticker；只做连续风险/趋势修正，不做 bull/bear 二元判断。默认 ^GSPC。",)
    group.add_argument("--ps-max-weight", type=float, default=None,
        dest="ps_max_target_weight", help="覆盖全局最高目标仓位，例如 0.8。默认使用策略档位。")
    group.add_argument("--ps-add-max", type=float, default=None,
        dest="ps_add_max_pct", help="覆盖单次加仓上限百分比，同时作用于普通、回调和弱趋势软量能加仓。")

    _add_legacy_portfolio_state_policy_args(group)


def _add_legacy_portfolio_state_policy_args(group) -> None:
    """Keep old detailed flags working without showing them in --help."""
    hidden = argparse.SUPPRESS
    group.add_argument("--ps-profile", choices=sorted(_PROFILE_PRESETS), default=None,
        help=hidden)
    group.add_argument("--ps-signal-sensitivity", type=float, default=None,
        help=hidden)
    group.add_argument("--ps-index-strength", choices=sorted(_INDEX_STRENGTH_PRESETS), default=None,
        help=hidden)
    group.add_argument("--ps-trend-weight", type=float, default=None,
        dest="ps_trend_score_weight", help=hidden)
    group.add_argument("--ps-momentum-weight", type=float, default=None,
        dest="ps_momentum_score_weight", help=hidden)
    group.add_argument("--ps-event-weight", type=float, default=None,
        dest="ps_event_score_weight", help=hidden)
    group.add_argument("--ps-risk-weight", type=float, default=None,
        dest="ps_risk_score_weight", help=hidden)
    group.add_argument("--ps-strong-floor", type=float, default=None,
        dest="ps_strong_uptrend_floor", help=hidden)
    group.add_argument("--ps-strong-cap", type=float, default=None,
        dest="ps_strong_uptrend_cap", help=hidden)
    group.add_argument("--ps-weak-floor", type=float, default=None,
        dest="ps_weak_uptrend_floor", help=hidden)
    group.add_argument("--ps-weak-cap", type=float, default=None,
        dest="ps_weak_uptrend_cap", help=hidden)
    group.add_argument("--ps-range-cap", type=float, default=None,
        dest="ps_range_cap", help=hidden)
    group.add_argument("--ps-event-cap", type=float, default=None,
        dest="ps_event_driven_cap", help=hidden)
    group.add_argument("--ps-min-trade-weight", type=float, default=None,
        dest="ps_min_trade_weight", help=hidden)
    group.add_argument("--ps-order-size-mult", type=float, default=None,
        dest="ps_order_size_multiplier", help=hidden)
    group.add_argument("--ps-recent-phase-lookback", type=int, default=None,
        dest="ps_recent_phase_lookback", help=hidden)
    group.add_argument("--ps-hysteresis-confirm", type=int, default=None,
        dest="ps_hysteresis_confirmation_count", help=hidden)
    group.add_argument("--ps-overextended-atr", type=float, default=None,
        dest="ps_overextended_sma20_atr_threshold", help=hidden)
    group.add_argument("--ps-stop-atr", type=float, default=None,
        dest="ps_stop_loss_atr_multiple", help=hidden)
    group.add_argument("--ps-trend-tp-atr", type=float, default=None,
        dest="ps_trend_take_profit_atr_multiple", help=hidden)
    group.add_argument("--ps-default-tp-atr", type=float, default=None,
        dest="ps_default_take_profit_atr_multiple", help=hidden)
    group.add_argument("--ps-trend-tp-high-mult", type=float, default=None,
        dest="ps_trend_take_profit_recent_high_multiplier", help=hidden)
    group.add_argument("--ps-default-add-max", type=float, default=None,
        dest="ps_default_add_max_pct", help=hidden)
    group.add_argument("--ps-pullback-add-max", type=float, default=None,
        dest="ps_pullback_entry_add_max_pct", help=hidden)
    group.add_argument("--ps-bearish-div-reduce", type=float, default=None,
        dest="ps_bearish_divergence_reduce_pct", help=hidden)
    group.add_argument("--ps-soft-volume-mult", type=float, default=None,
        dest="ps_volume_soft", help=hidden)
    group.add_argument("--ps-shrinking-volume-mult", type=float, default=None,
        dest="ps_volume_shrinking", help=hidden)
    group.add_argument("--ps-unavailable-volume-mult", type=float, default=None,
        dest="ps_volume_unavailable", help=hidden)
    group.add_argument("--ps-disable-index-context", action="store_true",
        dest="ps_disable_market_context", help=hidden)
    group.add_argument("--ps-index-bear-mult", type=float, default=None,
        dest="ps_market_context_bearish_weight_multiplier", help=hidden)
    group.add_argument("--ps-index-bull-mult", type=float, default=None,
        dest="ps_market_context_bullish_weight_multiplier", help=hidden)


def portfolio_state_policy_config_from_args(args) -> dict[str, Any]:
    """Build a sparse portfolio_state_policy config dict from argparse args."""
    config: dict[str, Any] = {}
    profile = getattr(args, "ps_profile", None)
    trade_frequency = getattr(args, "ps_trade_frequency", "normal")
    index_strength = getattr(args, "ps_index_strength", None)

    if profile:
        config.update(_PROFILE_PRESETS[profile])
    config.update(_TRADE_FREQUENCY_PRESETS[trade_frequency])
    if index_strength:
        config.update(_INDEX_STRENGTH_PRESETS[index_strength])

    sensitivity = getattr(args, "ps_signal_sensitivity", None)
    if sensitivity is not None:
        if sensitivity <= 0:
            raise ValueError("--ps-signal-sensitivity must be > 0")
        defaults = asdict(PortfolioStatePolicyConfig())
        for key in (
            "trend_score_weight",
            "momentum_score_weight",
            "event_score_weight",
            "risk_score_weight",
        ):
            base = float(config.get(key, defaults[key]))
            config[key] = base * sensitivity

    market_context_ticker = getattr(args, "ps_market_context_ticker", None)
    if market_context_ticker is not None:
        config["market_context_ticker"] = market_context_ticker

    max_target_weight = getattr(args, "ps_max_target_weight", None)
    if max_target_weight is not None:
        config["max_target_weight"] = max_target_weight

    stop_loss_atr_multiple = getattr(args, "ps_stop_loss_atr_multiple", None)
    if stop_loss_atr_multiple is not None:
        config["stop_loss_atr_multiple"] = stop_loss_atr_multiple

    add_max_pct = getattr(args, "ps_add_max_pct", None)
    if add_max_pct is not None:
        config["default_add_max_pct"] = add_max_pct
        config["pullback_entry_add_max_pct"] = add_max_pct
        config["weak_uptrend_soft_volume_add_max_pct"] = add_max_pct

    legacy_mapping = {
        "ps_trend_score_weight": "trend_score_weight",
        "ps_momentum_score_weight": "momentum_score_weight",
        "ps_event_score_weight": "event_score_weight",
        "ps_risk_score_weight": "risk_score_weight",
        "ps_strong_uptrend_floor": "strong_uptrend_floor",
        "ps_strong_uptrend_cap": "strong_uptrend_cap",
        "ps_weak_uptrend_floor": "weak_uptrend_floor",
        "ps_weak_uptrend_cap": "weak_uptrend_cap",
        "ps_range_cap": "range_cap",
        "ps_event_driven_cap": "event_driven_cap",
        "ps_max_target_weight": "max_target_weight",
        "ps_min_trade_weight": "min_trade_weight",
        "ps_order_size_multiplier": "order_size_multiplier",
        "ps_recent_phase_lookback": "recent_phase_lookback",
        "ps_hysteresis_confirmation_count": "hysteresis_confirmation_count",
        "ps_overextended_sma20_atr_threshold": "overextended_sma20_atr_threshold",
        "ps_stop_loss_atr_multiple": "stop_loss_atr_multiple",
        "ps_trend_take_profit_atr_multiple": "trend_take_profit_atr_multiple",
        "ps_default_take_profit_atr_multiple": "default_take_profit_atr_multiple",
        "ps_trend_take_profit_recent_high_multiplier": (
            "trend_take_profit_recent_high_multiplier"
        ),
        "ps_default_add_max_pct": "default_add_max_pct",
        "ps_pullback_entry_add_max_pct": "pullback_entry_add_max_pct",
        "ps_bearish_divergence_reduce_pct": "bearish_divergence_reduce_pct",
        "ps_market_context_ticker": "market_context_ticker",
    }
    for arg_name, config_name in legacy_mapping.items():
        value = getattr(args, arg_name, None)
        if value is not None:
            config[config_name] = value

    volume_overrides = {
        "soft": getattr(args, "ps_volume_soft", None),
        "shrinking": getattr(args, "ps_volume_shrinking", None),
        "unavailable": getattr(args, "ps_volume_unavailable", None),
    }
    volume_multipliers = {
        key: value for key, value in volume_overrides.items() if value is not None
    }
    if volume_multipliers:
        config["volume_multipliers"] = volume_multipliers

    if getattr(args, "ps_disable_market_context", False):
        config["market_context_enabled"] = False

    return config


def coerce_portfolio_state_policy_config(
    value: Optional[dict[str, Any] | PortfolioStatePolicyConfig],
) -> PortfolioStatePolicyConfig:
    if isinstance(value, PortfolioStatePolicyConfig):
        return value
    if not value:
        return PortfolioStatePolicyConfig()

    defaults = asdict(PortfolioStatePolicyConfig())
    merged = defaults.copy()
    valid_keys = {item.name for item in fields(PortfolioStatePolicyConfig)}
    merged.update({key: item for key, item in value.items() if key in valid_keys})
    volume_multipliers = defaults["volume_multipliers"].copy()
    volume_multipliers.update(value.get("volume_multipliers") or {})
    merged["volume_multipliers"] = volume_multipliers
    merged["phase_modifiers"] = value.get("phase_modifiers") or {}
    return PortfolioStatePolicyConfig(**merged)
