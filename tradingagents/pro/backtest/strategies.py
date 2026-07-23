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
    "RULES_V1_PARAMS",
    "PipelineStrategy",
    "apply_rules_v1_params",
]
