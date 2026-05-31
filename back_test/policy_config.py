"""PortfolioState policy configuration.

Holds the dataclass + CLI argparse glue for the deterministic policy used
by the backtest-only portfolio_state_manager. Kept separate from the agent
implementation so the agent module stays focused on decisions, not on how
to be CLI-configured.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Iterable, Optional


def _opt(default, low, high, dtype="float"):
    """Helper: mark a dataclass field as optimizable with continuous bounds.

    metadata keys:
        optimizable: True ⇒ included in to_vector / from_vector
        bounds:      (low, high) inclusive, used to clip from_vector input
        dtype:       "float" or "int" (ints are rounded in from_vector)
    """
    return field(
        default=default,
        metadata={"optimizable": True, "bounds": (low, high), "dtype": dtype},
    )


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
    "bull_pullback":          {"floor": 0.35, "cap": 0.85, "tp_size": 15.0, "allow_add": True,  "pullback_buy": True},
    "late_bull_distribution": {"cap": 0.25, "tp_size": 50.0, "allow_add": False, "block_new_position": True},
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

    # 趋势方向对目标仓位的贡献权重。
    trend_score_weight: float = _opt(0.25, 0.0, 1.0)
    # 动量强弱对目标仓位的贡献权重。
    momentum_score_weight: float = _opt(0.125, 0.0, 1.0)
    # 事件影响对目标仓位的贡献权重。
    event_score_weight: float = _opt(0.075, 0.0, 1.0)
    # 风险压力对目标仓位的扣减权重。
    risk_score_weight: float = _opt(0.48, 0.0, 1.0)

    # 强上升趋势中的最低目标仓位。
    strong_uptrend_floor: float = _opt(0.60, 0.0, 1.0)
    # 强上升趋势中的最高目标仓位。
    strong_uptrend_cap: float = _opt(1.00, 0.0, 1.0)
    # 弱上升趋势中的最低目标仓位。
    weak_uptrend_floor: float = _opt(0.15, 0.0, 1.0)
    # 弱上升趋势中的最高目标仓位。
    weak_uptrend_cap: float = _opt(0.30, 0.0, 1.0)
    # 震荡或不明朗状态中的最高目标仓位。
    range_cap: float = _opt(0.30, 0.0, 1.0)
    # 事件驱动状态中的最高目标仓位。
    event_driven_cap: float = _opt(0.60, 0.0, 1.0)
    # 成交量数据不可用时的最高目标仓位。
    unavailable_volume_cap: float = _opt(0.35, 0.0, 1.0)
    # 所有修正后的绝对最高目标仓位。
    max_target_weight: float = _opt(0.80, 0.0, 1.0)
    # 触发交易所需的最低目标仓位。
    min_trade_weight: float = _opt(0.02, 0.0, 0.5)
    # 对最终订单大小应用的整体乘数。
    order_size_multiplier: float = _opt(0.80, 0.0, 2.0)

    # 不同成交量状态下的目标仓位乘数。
    volume_multipliers: dict[str, float] = field(
        default_factory=lambda: {
            "expanding": 1.0,
            "normal": 1.0,
            "soft": 0.6,
            "shrinking": 0.35,
            "unavailable": 0.4,
        }
    )
    # 对默认市场阶段规则的可选覆盖。
    phase_modifiers: dict[str, dict[str, Any]] = field(default_factory=dict)

    # 用于滞后确认的历史阶段数量。
    recent_phase_lookback: int = _opt(2, 1, 10, dtype="int")
    # 确认突变阶段所需的次数。
    hysteresis_confirmation_count: int = _opt(0, 0, 5, dtype="int")
    # 判定过度上涨所需的 ATR 距离。值越小越尊重 LLM 的 overextended_bull 判断
    # （只有非常贴近 EMA5 时才降级到 healthy_bull_trend）。
    overextended_sma20_atr_threshold: float = _opt(0.8, 0.0, 5.0)
    # 上一笔以 stop_loss 退出后的冷却天数；空仓状态下在该窗口内不重新开仓。
    # 0 = 关闭。基于策略 as_of_date 与 trading_history 中最近一次 exit_date 的日历日差。
    post_stop_cooldown_days: int = _opt(3, 0, 30, dtype="int")

    # 回调买入时的单次最高加仓比例。
    pullback_entry_add_max_pct: float = _opt(12.0, 0.0, 100.0)
    # 将目标仓位转换为回调加仓比例的乘数。
    pullback_entry_add_weight_multiplier: float = _opt(60.0, 0.0, 200.0)
    # 普通加仓订单的单次最高加仓比例。
    default_add_max_pct: float = _opt(12.0, 0.0, 100.0)
    # 将目标仓位转换为普通加仓比例的乘数。
    default_add_weight_multiplier: float = _opt(50.0, 0.0, 200.0)
    # 弱上升趋势且量能偏软时的最高加仓比例。
    weak_uptrend_soft_volume_add_max_pct: float = _opt(4.0, 0.0, 100.0)

    # 加仓前是否要求“突破后回踩不破”或“连续收盘站稳关键位”等确认。
    add_requires_confirmation: bool = True
    # 加仓确认模式：pullback_or_close_hold / disabled。由策略生成端解释。
    add_confirmation_mode: str = "pullback_or_close_hold"
    # 回踩不破所需交易日数。
    add_pullback_hold_days: int = _opt(1, 1, 10, dtype="int")
    # 连续收盘站稳关键位所需交易日数。
    add_close_hold_days: int = _opt(2, 1, 10, dtype="int")
    # 关键位确认容忍度，0.005 = 允许 0.5% 噪声。
    add_key_level_tolerance_pct: float = _opt(0.005, 0.0, 0.05)

    # 整笔交易最大账户风险，0.020 = 账户权益 2%。
    max_trade_risk_pct: float = _opt(0.020, 0.0, 0.10)
    # 单次加仓最大权益占比。
    max_single_add_pct: float = _opt(8.0, 0.0, 100.0)
    # 加仓后总仓位最大权益占比。
    max_position_after_add_pct: float = _opt(0.60, 0.0, 1.0)
    # 每笔交易最多允许加仓次数。
    max_adds_per_trade: int = _opt(2, 0, 20, dtype="int")
    # 两次加仓之间至少间隔的交易日。
    min_days_between_adds: int = _opt(2, 0, 20, dtype="int")

    # 买入信号跳空追价保护。开盘高于计划买入价超过阈值则取消该订单。
    max_entry_gap_above_plan_pct: float = _opt(0.010, 0.0, 0.20)
    max_add_gap_above_plan_pct: float = _opt(0.008, 0.0, 0.20)
    allow_market_entry_gap_chase: bool = False

    # 旧信号有效期，按交易日计算。
    entry_signal_ttl_trading_days: int = _opt(2, 1, 20, dtype="int")
    add_signal_ttl_trading_days: int = _opt(1, 1, 20, dtype="int")
    take_profit_signal_ttl_trading_days: int = _opt(5, 1, 60, dtype="int")
    reduce_stop_signal_ttl_trading_days: int = _opt(3, 1, 60, dtype="int")

    # 加仓/建仓后按整笔风险上限重新抬高止损。
    recalculate_stop_after_add: bool = True
    stop_policy_after_add: str = "risk_capped"

    # 明显牛市时启用顺趋势覆盖：放宽追买、加仓和止盈距离，但执行层风险上限仍生效。
    obvious_bull_trend_following_enabled: bool = True
    obvious_bull_min_trend_direction: float = _opt(0.55, 0.0, 1.0)
    obvious_bull_min_trend_strength: float = _opt(0.65, 0.0, 1.0)
    obvious_bull_min_momentum: float = _opt(0.45, 0.0, 1.0)
    obvious_bull_max_risk_pressure: float = _opt(0.45, 0.0, 1.0)
    obvious_bull_min_confidence: float = _opt(0.60, 0.0, 1.0)
    obvious_bull_add_max_pct: float = _opt(15.0, 0.0, 100.0)
    obvious_bull_position_cap: float = _opt(0.85, 0.0, 1.0)
    obvious_bull_take_profit_atr_multiple: float = _opt(3.5, 0.1, 10.0)
    obvious_bull_take_profit_size_pct: float = _opt(10.0, 0.0, 100.0)
    obvious_bull_recent_high_multiplier: float = _opt(1.03, 1.0, 2.0)
    obvious_bull_relax_add_confirmation: bool = False
    obvious_bull_allow_market_entry: bool = True
    obvious_bull_allow_entry_gap_chase: bool = True
    obvious_bull_allow_add_gap_chase: bool = False
    obvious_bull_max_entry_gap_pct: float = _opt(0.015, 0.0, 0.20)
    obvious_bull_max_add_gap_pct: float = _opt(0.005, 0.0, 0.20)

    # 出现 bearish 成交量背离时的减仓比例。
    bearish_divergence_reduce_pct: float = _opt(30.0, 0.0, 100.0)
    # bearish 背离保护止损使用的 ATR 倍数。
    bearish_divergence_stop_atr: float = _opt(1.5, 0.1, 10.0)
    # bearish 背离且无支撑位时的备用 ATR 倍数。
    bearish_divergence_fallback_stop_atr: float = _opt(2.0, 0.1, 10.0)
    # 标准止损位置使用的 ATR 倍数。
    stop_loss_atr_multiple: float = _opt(1.3, 0.1, 10.0)
    # 趋势止盈位置使用的 ATR 倍数。
    trend_take_profit_atr_multiple: float = _opt(2.2, 0.1, 10.0)
    # 用近期高点上浮来拉远趋势止盈的位置。
    trend_take_profit_recent_high_multiplier: float = _opt(1.01, 1.0, 2.0)
    # 非趋势止盈位置使用的 ATR 倍数。
    default_take_profit_atr_multiple: float = _opt(1.8, 0.1, 10.0)
    # 强上升趋势中的止盈卖出比例。
    strong_uptrend_take_profit_size_pct: float = _opt(25.0, 0.0, 100.0)
    # 默认止盈卖出比例。
    default_take_profit_size_pct: float = _opt(40.0, 0.0, 100.0)
    # 是否用大盘状态修正个股决策。
    market_context_enabled: bool = True
    # 作为大盘上下文来源的 ticker。
    market_context_ticker: str = "^GSPC"

    def merged_phase_modifiers(self) -> dict[str, dict[str, Any]]:
        merged = {phase: values.copy() for phase, values in _DEFAULT_PHASE_MODIFIER.items()}
        for phase, values in self.phase_modifiers.items():
            base = merged.setdefault(phase, {})
            base.update(values)
        return merged


def optimizable_field_names() -> list[str]:
    """Names of dataclass fields marked optimizable, in declaration order.

    Stable across runs as long as the dataclass definition doesn't change —
    safe to use as the canonical index for to_vector / from_vector vectors.
    """
    return [f.name for f in fields(PortfolioStatePolicyConfig)
            if f.metadata.get("optimizable")]


def optimizable_bounds() -> list[tuple[float, float]]:
    """(low, high) pairs aligned with optimizable_field_names()."""
    return [f.metadata["bounds"] for f in fields(PortfolioStatePolicyConfig)
            if f.metadata.get("optimizable")]


def optimizable_dtypes() -> list[str]:
    """"float" / "int" tags aligned with optimizable_field_names()."""
    return [f.metadata["dtype"] for f in fields(PortfolioStatePolicyConfig)
            if f.metadata.get("optimizable")]


def to_vector(cfg: PortfolioStatePolicyConfig) -> list[float]:
    """Extract optimizable params as a flat list[float] in declaration order.

    Returned as plain list so callers can wrap in numpy / torch / jax without
    pulling those into this module.
    """
    return [float(getattr(cfg, name)) for name in optimizable_field_names()]


def from_vector(
    vec: Iterable[float],
    base: Optional[PortfolioStatePolicyConfig] = None,
) -> PortfolioStatePolicyConfig:
    """Build a config from a flat vector of optimizable values.

    - Values are clipped into each field's declared bounds.
    - Fields tagged dtype="int" are rounded.
    - Non-optimizable fields (volume_multipliers, phase_modifiers,
      market_context_enabled, market_context_ticker) are copied from `base`,
      or take dataclass defaults if `base` is None.
    """
    values = list(vec)
    names = optimizable_field_names()
    if len(values) != len(names):
        raise ValueError(
            f"from_vector expected {len(names)} values, got {len(values)}"
        )

    base_dict = asdict(base) if base is not None else asdict(PortfolioStatePolicyConfig())
    overrides: dict[str, Any] = {}
    for name, raw, (low, high), dtype in zip(
        names, values, optimizable_bounds(), optimizable_dtypes()
    ):
        clipped = min(max(float(raw), low), high)
        overrides[name] = int(round(clipped)) if dtype == "int" else clipped

    base_dict.update(overrides)
    return PortfolioStatePolicyConfig(**base_dict)


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
        "weak_uptrend_floor": 0.13,
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
    group.add_argument("--ps-max-trade-risk", type=float, default=None,
        dest="ps_max_trade_risk_pct", help="整笔交易最大账户风险，例如 0.020 表示 2%。")
    group.add_argument("--ps-add-ttl", type=int, default=None,
        dest="ps_add_signal_ttl_trading_days", help="加仓信号有效交易日数，默认 1。")
    group.add_argument("--ps-entry-ttl", type=int, default=None,
        dest="ps_entry_signal_ttl_trading_days", help="建仓信号有效交易日数，默认 2。")
    group.add_argument("--ps-add-gap", type=float, default=None,
        dest="ps_max_add_gap_above_plan_pct", help="加仓开盘跳空高于计划价的放弃阈值，默认 0.008。")
    group.add_argument("--ps-obvious-bull", action="store_true",
        dest="ps_obvious_bull_trend_following_enabled", help="明显牛市时启用顺趋势覆盖，放宽追买、加仓和止盈。")
    group.add_argument("--ps-obvious-bull-add-max", type=float, default=None,
        dest="ps_obvious_bull_add_max_pct", help="明显牛市下单次加仓上限百分比，默认 15。")
    group.add_argument("--ps-obvious-bull-cap", type=float, default=None,
        dest="ps_obvious_bull_position_cap", help="明显牛市下目标仓位上限，默认 0.85。")
    group.add_argument("--ps-obvious-bull-entry-gap", type=float, default=None,
        dest="ps_obvious_bull_max_entry_gap_pct", help="明显牛市下建仓可追跳空阈值，默认 0.015。")
    group.add_argument("--ps-obvious-bull-add-gap", type=float, default=None,
        dest="ps_obvious_bull_max_add_gap_pct", help="明显牛市下加仓可接受跳空阈值，默认 0.005。")

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
        "ps_max_trade_risk_pct": "max_trade_risk_pct",
        "ps_add_signal_ttl_trading_days": "add_signal_ttl_trading_days",
        "ps_entry_signal_ttl_trading_days": "entry_signal_ttl_trading_days",
        "ps_max_add_gap_above_plan_pct": "max_add_gap_above_plan_pct",
        "ps_obvious_bull_add_max_pct": "obvious_bull_add_max_pct",
        "ps_obvious_bull_position_cap": "obvious_bull_position_cap",
        "ps_obvious_bull_max_entry_gap_pct": "obvious_bull_max_entry_gap_pct",
        "ps_obvious_bull_max_add_gap_pct": "obvious_bull_max_add_gap_pct",
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

    if getattr(args, "ps_obvious_bull_trend_following_enabled", False):
        config["obvious_bull_trend_following_enabled"] = True

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
