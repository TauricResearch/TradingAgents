"""Built-in strategies (roadmap P0.3 / architecture track T1).

The existing rules engine — the whole deterministic pipeline (evidence votes
-> consensus judge -> risk + quality gates -> portfolio_manager building a
sized TradeRecommendation) — wrapped under the Strategy SDK as ``rules_v1``.

Faithfulness is by delegation, not reimplementation: ``PipelineStrategy``
runs the *same* compiled pipeline the engine runs today and hands the engine
the *same* state dict (recommendation / rejection / HOLD), so trades, R
accounting, and rejection tallies are bit-for-bit identical to a direct
``BacktestEngine(RulesPipelineLLM(), ...)`` run at default params (locked by
tests/test_pro_strategy_equivalence.py). Only genuinely-wired knobs are
exposed as tunables — the R-ladder, the min-R:R gate, and the stop-out
cooldown — each of which already flows through ``config.risk`` into the
pipeline/engine, so a non-default value truly changes behavior (no
decorative parameters).

``pipeline_llm`` (the real-LLM path) needs the operator's model bundle, which
is environment, not a tunable — it is registered by the dashboard job that
owns the bundle (a later increment), not here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tradingagents.pro.backtest.registry import register
from tradingagents.pro.backtest.strategy import (
    BracketIntent,
    OrderIntent,
    Param,
    ParamSpace,
    StrategyContext,
)

if TYPE_CHECKING:
    from tradingagents.contracts import ProConfig

# R-ladder presets exposed as a categorical param. Each maps to
# (r_multiples, fractions) — the same shape RiskLimits carries. The default
# reproduces the shipped ladder exactly (planned R:R 2.0, ~67% structural).
_TP_LADDERS: dict[str, tuple[list[float], list[float]]] = {
    "0.5/3.5": ([0.5, 3.5], [0.5, 0.5]),
    "1.0/3.0": ([1.0, 3.0], [0.5, 0.5]),
    "1.5/3.0": ([1.5, 3.0], [0.5, 0.5]),
}

RULES_V1_PARAMS = ParamSpace(
    Param("tp_ladder", "categorical", choices=tuple(_TP_LADDERS), default="0.5/3.5"),
    Param("min_risk_reward", "float", 1.2, 2.5, step=0.1, default=1.8),
    Param("stop_cooldown_bars", "int", 0, 20, default=10),
)


def apply_rules_v1_params(config: ProConfig, params: dict[str, Any]) -> ProConfig:
    """Return a copy of ``config`` with the rules_v1 params patched onto
    ``config.risk``. At default params this is a value-identical copy (so
    equivalence holds); a non-default ladder / min-R:R / cooldown genuinely
    changes the pipeline geometry, the quality gate, and the engine cooldown
    respectively — all already wired to these RiskLimits fields."""
    r_multiples, fractions = _TP_LADDERS[params["tp_ladder"]]
    risk = config.risk.model_copy(update={
        "tp_r_multiples": list(r_multiples),
        "tp_fractions": list(fractions),
        "min_risk_reward": params["min_risk_reward"],
        "stop_cooldown_bars": params["stop_cooldown_bars"],
    })
    return config.model_copy(update={"risk": risk})


class PipelineStrategy:
    """Strategy SDK adapter over a compiled Pro pipeline.

    Satisfies the ``Strategy`` protocol AND exposes ``decide`` — the engine
    drives pipeline-backed strategies through ``decide`` (which returns the
    full pipeline state, preserving rejection/HOLD accounting), while
    ``on_bar`` provides the protocol's native-intent view for future
    order-lifecycle execution (P1) and unit tests.

    ``bind`` is called once by the engine with the run's config/memory so the
    strategy can build its pipeline with its params applied. A rules_v1
    strategy supplies ``RulesPipelineLLM`` as its own model, so it needs no
    external LLM; ``pipeline_llm`` supplies the operator's bundle at bind.
    """

    def __init__(
        self,
        strategy_id: str,
        params: dict[str, Any],
        *,
        llm_factory,
        config_patch=None,
    ):
        self.id = strategy_id
        self.params = params  # resolved dict (the protocol's declared space
        # lives on the registered ParamSpace; instances carry resolved values)
        self._llm_factory = llm_factory
        self._config_patch = config_patch
        self._pipeline = None
        self._config: ProConfig | None = None
        self._last_state: dict | None = None

    # --- engine lifecycle ----------------------------------------------------

    def bind(self, config: ProConfig, memory=None, **pipeline_kwargs) -> ProConfig:
        """Build the pipeline with this strategy's params applied to ``config``.
        Returns the (possibly patched) config so the engine uses the same
        RiskLimits the pipeline was built with (the cooldown check reads it)."""
        from tradingagents.pro.pipeline import build_pro_pipeline

        patched = self._config_patch(config, self.params) if self._config_patch else config
        self._config = patched
        self._pipeline = build_pro_pipeline(
            self._llm_factory(), patched, memory=memory, **pipeline_kwargs)
        return patched

    def decide(self, snapshot, equity: float) -> dict:
        """Run the pipeline for one bar; return its state dict (recommendation /
        rejection / HOLD) — exactly what the engine consumes today."""
        if self._pipeline is None:
            raise RuntimeError("strategy.bind must be called before decide")
        self._last_state = self._pipeline.invoke(
            {"snapshot": snapshot, "equity": equity})
        return self._last_state

    # --- Strategy protocol ---------------------------------------------------

    def on_start(self, ctx: StrategyContext) -> None:  # noqa: D401
        """No per-run setup beyond bind."""

    def on_bar(self, ctx: StrategyContext) -> list[OrderIntent]:
        """Native-intent view: run the pipeline and translate a directional
        recommendation into a market bracket intent. The engine uses ``decide``
        for pipeline strategies (bit-for-bit), so this is for native execution
        (P1) and tests — it carries the sized quantity + bracket geometry."""
        state = self.decide(ctx.snapshot, ctx.equity)
        rec = state.get("recommendation")
        from tradingagents.contracts import TradeAction

        if rec is None or rec.action is TradeAction.HOLD:
            return []
        return [OrderIntent(
            kind="market",
            side=rec.action.value,
            quantity=rec.position_size.quantity,
            bracket=BracketIntent(
                stop_loss=rec.stop_loss,
                take_profits=tuple((tp.price, tp.size_fraction)
                                   for tp in rec.take_profits)),
            tag=rec.id,
        )]

    def on_fill(self, fill) -> None:  # noqa: D401
        """Rules strategy holds no per-fill state."""

    def on_stop(self, ctx: StrategyContext) -> None:  # noqa: D401
        """No teardown."""


# --- trend_following_v1: native order-book strategy (the KB's #1 pattern) -----

TREND_V1_PARAMS = ParamSpace(
    Param("donchian_period", "int", 10, 100, default=20),
    Param("stop_atr_mult", "float", 1.5, 4.0, step=0.5, default=2.0),
    Param("trail_pct", "float", 0.01, 0.10, step=0.01, default=0.05),
    Param("risk_pct", "float", 0.1, 3.0, step=0.1, default=1.0),
    Param("allow_short", "categorical", choices=("yes", "no"), default="yes"),
)


class TrendFollowingV1:
    """Donchian-channel breakout with a volatility (ATR) stop and a percentage
    trailing exit — a runnable reference implementation of the systematic
    trend-following package that recurred most strongly in the trader research
    (docs/research/02_pattern_report.md: channel breakout + ATR stop, lift 10.6;
    trend-following + vol-normalized sizing, the highest-support pattern).

    A NATIVE strategy: it emits OrderIntents from on_bar (executed through the
    broker's pending-order book), so it needs no LLM/pipeline. Everything is
    computed from the look-ahead-safe snapshot window (bars <= current)."""

    def __init__(self, params: dict[str, Any]):
        self.id = "trend_following_v1"
        self.params = params

    def on_start(self, ctx: StrategyContext) -> None: ...

    def on_bar(self, ctx: StrategyContext) -> list[OrderIntent]:
        bars = ctx.snapshot.bars
        period = int(self.params["donchian_period"])
        if len(bars) < period + 2:
            return []
        atr = self._atr(bars, period)
        if atr <= 0:
            return []
        last = bars[-1]
        prior = bars[-(period + 1):-1]  # the N bars BEFORE the current one
        prior_high = max(b.high for b in prior)
        prior_low = min(b.low for b in prior)
        open_sides = {p.side for p in ctx.positions}  # one position per side
        mult = float(self.params["stop_atr_mult"])
        trail = float(self.params["trail_pct"])
        risk = float(self.params["risk_pct"])

        if last.close > prior_high and "BUY" not in open_sides:
            return [self._entry("BUY", last.close, last.close - mult * atr,
                                last.close + 20 * atr, trail, risk)]
        if (self.params["allow_short"] == "yes"
                and last.close < prior_low and "SELL" not in open_sides):
            return [self._entry("SELL", last.close, last.close + mult * atr,
                                last.close - 20 * atr, trail, risk)]
        return []

    def on_fill(self, fill) -> None: ...

    def on_stop(self, ctx: StrategyContext) -> None: ...

    @staticmethod
    def _atr(bars, period: int) -> float:
        recent = bars[-(period + 1):]
        trs = [max(c.high - c.low, abs(c.high - p.close), abs(c.low - p.close))
               for p, c in zip(recent, recent[1:], strict=False)]
        return sum(trs) / len(trs) if trs else 0.0

    @staticmethod
    def _entry(side, ref, stop, target, trail, risk) -> OrderIntent:
        # confirm the breakout on this bar's close, enter market at the next
        # bar's open; ride the trailing stop (far TP so trailing is the exit)
        return OrderIntent(
            kind="market", side=side, risk_pct=risk,
            bracket=BracketIntent(stop_loss=stop, take_profits=((target, 1.0),),
                                  trailing="pct", trailing_mult=trail),
            tag=f"tf_{side.lower()}")


@register("trend_following_v1", TREND_V1_PARAMS,
          description="Donchian-channel breakout with an ATR stop and a "
                      "percentage trailing exit — a native order-book strategy "
                      "(long & short). Reference implementation of the research's "
                      "top systematic trend-following pattern. No model calls.")
def _build_trend_following_v1(params: dict[str, Any]) -> TrendFollowingV1:
    return TrendFollowingV1(params)


MEAN_REVERSION_V1_PARAMS = ParamSpace(
    Param("lookback", "int", 10, 60, default=20),
    Param("entry_std", "float", 1.5, 3.0, step=0.5, default=2.0),
    Param("stop_atr_mult", "float", 1.5, 4.0, step=0.5, default=3.0),
    Param("risk_pct", "float", 0.1, 3.0, step=0.1, default=1.0),
    Param("allow_short", "categorical", choices=("yes", "no"), default="yes"),
)


class MeanReversionV1:
    """Bollinger-style mean reversion — fade a stretch beyond ``entry_std``
    standard deviations from the SMA, target the mean, and stop on a further
    ATR move against the entry. The counter-trend package that recurs in the
    trader research (docs/research/02_pattern_report.md) — the natural
    complement to trend_following_v1, and a second real consumer of the native
    order-book path. Everything is computed from the look-ahead-safe snapshot
    window (bars <= current)."""

    def __init__(self, params: dict[str, Any]):
        self.id = "mean_reversion_v1"
        self.params = params

    def on_start(self, ctx: StrategyContext) -> None: ...

    def on_bar(self, ctx: StrategyContext) -> list[OrderIntent]:
        bars = ctx.snapshot.bars
        n = int(self.params["lookback"])
        if len(bars) < n + 2:
            return []
        closes = [b.close for b in bars[-n:]]
        sma = sum(closes) / n
        std = (sum((c - sma) ** 2 for c in closes) / n) ** 0.5
        atr = self._atr(bars, n)
        if std <= 0 or atr <= 0:
            return []
        last = bars[-1]
        k = float(self.params["entry_std"])
        lower, upper = sma - k * std, sma + k * std
        mult = float(self.params["stop_atr_mult"])
        risk = float(self.params["risk_pct"])
        open_sides = {p.side for p in ctx.positions}  # one position per side

        # stretched BELOW the band → fade up toward the mean (target = SMA)
        if last.close < lower and "BUY" not in open_sides:
            return [self._entry("BUY", last.close - mult * atr, sma, risk)]
        if (self.params["allow_short"] == "yes"
                and last.close > upper and "SELL" not in open_sides):
            return [self._entry("SELL", last.close + mult * atr, sma, risk)]
        return []

    def on_fill(self, fill) -> None: ...

    def on_stop(self, ctx: StrategyContext) -> None: ...

    @staticmethod
    def _atr(bars, period: int) -> float:
        recent = bars[-(period + 1):]
        trs = [max(c.high - c.low, abs(c.high - p.close), abs(c.low - p.close))
               for p, c in zip(recent, recent[1:], strict=False)]
        return sum(trs) / len(trs) if trs else 0.0

    @staticmethod
    def _entry(side, stop, target, risk) -> OrderIntent:
        # enter market at the next bar's open; the single target is the mean
        # (no trailing — mean reversion exits at the mean or the stop)
        return OrderIntent(
            kind="market", side=side, risk_pct=risk,
            bracket=BracketIntent(stop_loss=stop, take_profits=((target, 1.0),)),
            tag=f"mr_{side.lower()}")


@register("mean_reversion_v1", MEAN_REVERSION_V1_PARAMS,
          description="Bollinger-style mean reversion — fade a move beyond N "
                      "standard deviations from the SMA, target the mean, ATR "
                      "stop (long & short). A native order-book strategy "
                      "implementing the research's counter-trend pattern. No "
                      "model calls.")
def _build_mean_reversion_v1(params: dict[str, Any]) -> MeanReversionV1:
    return MeanReversionV1(params)


MOMENTUM_V1_PARAMS = ParamSpace(
    Param("roc_period", "int", 5, 40, default=14),
    Param("roc_threshold", "float", 1.0, 15.0, step=1.0, default=5.0),
    Param("stop_atr_mult", "float", 1.0, 4.0, step=0.5, default=2.0),
    Param("target_atr_mult", "float", 1.0, 6.0, step=0.5, default=3.0),
    Param("risk_pct", "float", 0.1, 3.0, step=0.1, default=1.0),
    Param("allow_short", "categorical", choices=("yes", "no"), default="yes"),
)


class MomentumV1:
    """Rate-of-change momentum — enter in the direction of a strong recent move
    (|ROC| over ``roc_period`` beyond ``roc_threshold`` percent) and take a
    FIXED-R outcome (ATR stop + ATR target, no trailing). Distinct from the
    breakout (channel + trailing) and mean-reversion (fade the mean) packages;
    the momentum/relative-strength archetype from the research. Long & short,
    computed from the look-ahead-safe snapshot window."""

    def __init__(self, params: dict[str, Any]):
        self.id = "momentum_v1"
        self.params = params

    def on_start(self, ctx: StrategyContext) -> None: ...

    def on_bar(self, ctx: StrategyContext) -> list[OrderIntent]:
        bars = ctx.snapshot.bars
        p = int(self.params["roc_period"])
        if len(bars) < p + 2:
            return []
        atr = self._atr(bars, p)
        ref = bars[-(p + 1)]
        if atr <= 0 or ref.close <= 0:
            return []
        last = bars[-1]
        roc = (last.close / ref.close - 1.0) * 100.0
        thr = float(self.params["roc_threshold"])
        stop_m = float(self.params["stop_atr_mult"])
        tgt_m = float(self.params["target_atr_mult"])
        risk = float(self.params["risk_pct"])
        open_sides = {pos.side for pos in ctx.positions}

        if roc > thr and "BUY" not in open_sides:
            return [self._entry("BUY", last.close - stop_m * atr,
                                last.close + tgt_m * atr, risk)]
        if (self.params["allow_short"] == "yes"
                and roc < -thr and "SELL" not in open_sides):
            return [self._entry("SELL", last.close + stop_m * atr,
                                last.close - tgt_m * atr, risk)]
        return []

    def on_fill(self, fill) -> None: ...

    def on_stop(self, ctx: StrategyContext) -> None: ...

    @staticmethod
    def _atr(bars, period: int) -> float:
        recent = bars[-(period + 1):]
        trs = [max(c.high - c.low, abs(c.high - p.close), abs(c.low - p.close))
               for p, c in zip(recent, recent[1:], strict=False)]
        return sum(trs) / len(trs) if trs else 0.0

    @staticmethod
    def _entry(side, stop, target, risk) -> OrderIntent:
        return OrderIntent(
            kind="market", side=side, risk_pct=risk,
            bracket=BracketIntent(stop_loss=stop, take_profits=((target, 1.0),)),
            tag=f"mom_{side.lower()}")


@register("momentum_v1", MOMENTUM_V1_PARAMS,
          description="Rate-of-change momentum — enter with a strong recent "
                      "move (ROC beyond a threshold) for a fixed-R ATR "
                      "stop/target (long & short). A native order-book strategy "
                      "implementing the research's momentum/relative-strength "
                      "pattern. No model calls.")
def _build_momentum_v1(params: dict[str, Any]) -> MomentumV1:
    return MomentumV1(params)


MA_CROSSOVER_V1_PARAMS = ParamSpace(
    Param("fast_period", "int", 5, 50, default=10),
    Param("slow_period", "int", 20, 200, default=30),
    Param("stop_atr_mult", "float", 1.5, 4.0, step=0.5, default=2.0),
    Param("trail_pct", "float", 0.01, 0.10, step=0.01, default=0.05),
    Param("risk_pct", "float", 0.1, 3.0, step=0.1, default=1.0),
    Param("allow_short", "categorical", choices=("yes", "no"), default="yes"),
)


class MaCrossoverV1:
    """Dual moving-average crossover — enter on the bar a fast SMA crosses
    the slow SMA (golden cross → long, death cross → short) and ride it with a
    percentage trailing stop off an ATR initial stop. The entry SIGNAL (a
    cross event) is distinct from the channel breakout, the σ-fade, and the
    ROC threshold — the canonical trend-change archetype. Computed from the
    look-ahead-safe snapshot window."""

    def __init__(self, params: dict[str, Any]):
        self.id = "ma_crossover_v1"
        self.params = params

    def on_start(self, ctx: StrategyContext) -> None: ...

    def on_bar(self, ctx: StrategyContext) -> list[OrderIntent]:
        bars = ctx.snapshot.bars
        f, s = int(self.params["fast_period"]), int(self.params["slow_period"])
        if f >= s or len(bars) < s + 2:
            return []
        closes = [b.close for b in bars]
        fast_now = sum(closes[-f:]) / f
        slow_now = sum(closes[-s:]) / s
        fast_prev = sum(closes[-(f + 1):-1]) / f
        slow_prev = sum(closes[-(s + 1):-1]) / s
        atr = self._atr(bars, s)
        if atr <= 0:
            return []
        last = bars[-1]
        mult = float(self.params["stop_atr_mult"])
        trail = float(self.params["trail_pct"])
        risk = float(self.params["risk_pct"])
        open_sides = {p.side for p in ctx.positions}

        cross_up = fast_prev <= slow_prev and fast_now > slow_now
        cross_down = fast_prev >= slow_prev and fast_now < slow_now
        if cross_up and "BUY" not in open_sides:
            return [self._entry("BUY", last.close - mult * atr,
                                last.close + 20 * atr, trail, risk)]
        if (self.params["allow_short"] == "yes"
                and cross_down and "SELL" not in open_sides):
            return [self._entry("SELL", last.close + mult * atr,
                                last.close - 20 * atr, trail, risk)]
        return []

    def on_fill(self, fill) -> None: ...

    def on_stop(self, ctx: StrategyContext) -> None: ...

    @staticmethod
    def _atr(bars, period: int) -> float:
        recent = bars[-(period + 1):]
        trs = [max(c.high - c.low, abs(c.high - p.close), abs(c.low - p.close))
               for p, c in zip(recent, recent[1:], strict=False)]
        return sum(trs) / len(trs) if trs else 0.0

    @staticmethod
    def _entry(side, stop, target, trail, risk) -> OrderIntent:
        return OrderIntent(
            kind="market", side=side, risk_pct=risk,
            bracket=BracketIntent(stop_loss=stop, take_profits=((target, 1.0),),
                                  trailing="pct", trailing_mult=trail),
            tag=f"xover_{side.lower()}")


@register("ma_crossover_v1", MA_CROSSOVER_V1_PARAMS,
          description="Dual moving-average crossover — enter on a fast/slow SMA "
                      "cross (golden → long, death → short) and ride it with a "
                      "percentage trailing stop off an ATR initial stop. A "
                      "native order-book strategy; the canonical trend-change "
                      "signal. No model calls.")
def _build_ma_crossover_v1(params: dict[str, Any]) -> MaCrossoverV1:
    return MaCrossoverV1(params)


def _rules_llm():
    from tradingagents.pro.evals.rules import RulesPipelineLLM

    return RulesPipelineLLM()


@register("rules_v1", RULES_V1_PARAMS,
          description="Deterministic indicator-rules pipeline (trend/momentum "
                      "votes, ADX chop filter, long & short) with an R-based "
                      "profit ladder and breakeven lock-in. No model calls.")
def _build_rules_v1(params: dict[str, Any]) -> PipelineStrategy:
    return PipelineStrategy(
        "rules_v1", params, llm_factory=_rules_llm,
        config_patch=apply_rules_v1_params)


__all__ = [
    "MA_CROSSOVER_V1_PARAMS",
    "MEAN_REVERSION_V1_PARAMS",
    "MOMENTUM_V1_PARAMS",
    "RULES_V1_PARAMS",
    "TREND_V1_PARAMS",
    "MaCrossoverV1",
    "MeanReversionV1",
    "MomentumV1",
    "PipelineStrategy",
    "TrendFollowingV1",
    "apply_rules_v1_params",
]
