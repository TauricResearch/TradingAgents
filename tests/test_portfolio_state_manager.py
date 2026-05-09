from types import SimpleNamespace

from back_test.policy_config import (
    PortfolioStatePolicyConfig,
    coerce_portfolio_state_policy_config,
)
from tradingagents.agents.managers.portfolio_state_manager import (
    MarketState,
    PortfolioStatePolicyConfig as ManagerPortfolioStatePolicyConfig,
    _fallback_market_state,
    _invoke_market_state,
    _market_state_response_to_model,
    policy_from_market_state,
)


def _market_state_json() -> str:
    return """{
      "schema_version": "state_v2",
      "ticker": "SPY",
      "as_of_date": "2024-01-02",
      "trend_regime": "ascending",
      "volatility_regime": "normal",
      "momentum_regime": "positive",
      "liquidity_regime": "volume_expansion",
      "event_regime": "none",
      "structure_quality": "coherent",
      "exhaustion_state": "none",
      "breadth_state": "broad_participation",
      "trend_direction_score": 0.7,
      "trend_strength": 0.85,
      "momentum_score_value": 0.6,
      "risk_pressure_score": 0.25,
      "event_impact_score": 0.1,
      "confidence": 0.8,
      "confidence_components": {
        "anchor_agreement": 0.85,
        "timeframe_consistency": 0.8,
        "volatility_stability": 0.8,
        "contradiction_absence": 0.75,
        "event_certainty": 0.8
      },
      "horizon_days": 10,
      "timeframe_hierarchy": {
        "higher_timeframe_trend": "ascending",
        "trading_timeframe_trend": "ascending",
        "lower_timeframe_trend": "ascending",
        "alignment": "aligned",
        "short_term_override": "none"
      },
      "invalidation": {
        "invalidation_type": "structure_break",
        "invalidation_detail": "Trading timeframe closes below the primary moving-average stack.",
        "reference_timeframe": "trading"
      },
      "evidence": {
        "hard_anchors": ["Price structure and EMA hierarchy align."],
        "event_modifiers": [],
        "narrative_residual": [],
        "contradictory_signals": []
      },
      "state_summary": "Trend structure is coherent with stable volatility.",
      "key_risks": ["Macro shock", "Volume fades"]
    }"""


def _anchors() -> dict:
    return {
        "current_price": 459.9912,
        "atr14": 3.863,
        "nearest_support": 459.7966,
        "nearest_resistance": 460.3124,
        "recent_high_20d": 464.76,
        "sma20": 454.7778,
        "sma50": 436.8196,
        "sma200": 420.1105,
        "volume_ratio": 1.528,
    }


def test_market_state_response_parses_free_text_json_content():
    response = SimpleNamespace(content=f"```json\n{_market_state_json()}\n```")

    state = _market_state_response_to_model(response)

    assert isinstance(state, MarketState)
    assert state.ticker == "SPY"
    assert state.trend_regime == "ascending"
    assert state.market_phase == "accelerating_bull"


def test_invoke_market_state_falls_back_when_structured_output_unsupported():
    class ReasonerLikeLLM:
        def with_structured_output(self, _schema):
            raise NotImplementedError("deepseek-reasoner does not support tool_choice")

        def invoke(self, _prompt):
            return SimpleNamespace(content=_market_state_json())

    state = _invoke_market_state(
        ReasonerLikeLLM(),
        "classify",
        "SPY",
        "2024-01-02",
        _anchors(),
        "expanding",
    )

    assert state.trend_regime == "ascending"
    assert state.regime == "strong_uptrend"
    assert state.confidence == 0.8


def test_invoke_market_state_skips_structured_for_deepseek_thinking_mode():
    class ThinkingLLM:
        model_name = "deepseek-v4-flash"
        extra_body = {"thinking": {"type": "enabled"}}

        def with_structured_output(self, _schema):
            raise AssertionError("structured output should be skipped")

        def invoke(self, _prompt):
            return SimpleNamespace(content=_market_state_json())

    state = _invoke_market_state(
        ThinkingLLM(),
        "classify",
        "SPY",
        "2024-01-02",
        _anchors(),
        "expanding",
    )

    assert state.trend_regime == "ascending"


def test_invoke_market_state_skips_structured_for_deepseek_flash_mode():
    class DeepSeekFlashLLM:
        model_name = "deepseek-v4-flash"
        extra_body = None

        def with_structured_output(self, _schema):
            raise AssertionError("structured output should be skipped")

        def invoke(self, _prompt):
            return SimpleNamespace(content=_market_state_json())

    state = _invoke_market_state(
        DeepSeekFlashLLM(),
        "classify",
        "SPY",
        "2024-01-02",
        _anchors(),
        "expanding",
    )

    assert state.trend_regime == "ascending"


def test_invoke_market_state_uses_anchor_fallback_for_invalid_json():
    class BadJsonLLM:
        def with_structured_output(self, _schema):
            raise NotImplementedError("unsupported")

        def invoke(self, _prompt):
            return SimpleNamespace(content="I cannot produce JSON here.")

    state = _invoke_market_state(
        BadJsonLLM(),
        "classify",
        "SPY",
        "2024-01-02",
        _anchors(),
        "expanding",
    )

    assert state.ticker == "SPY"
    assert state.regime == "strong_uptrend"
    assert state.market_phase == "accelerating_bull"
    assert state.confidence == 0.66


def test_fallback_market_state_is_valid_market_state():
    state = _fallback_market_state("SPY", "2024-01-02", _anchors(), "expanding")

    assert isinstance(state, MarketState)
    assert state.as_of_date == "2024-01-02"


def test_policy_config_moved_to_back_test_module_with_manager_compat_export():
    config = coerce_portfolio_state_policy_config(
        {"volume_multipliers": {"soft": 0.6}, "range_cap": 0.25}
    )

    assert ManagerPortfolioStatePolicyConfig is PortfolioStatePolicyConfig
    assert config.range_cap == 0.25
    assert config.volume_multipliers["soft"] == 0.6
    assert config.volume_multipliers["normal"] == 1.0


def test_market_context_continuous_risk_adjusts_new_stock_entry():
    stock_state = MarketState.model_validate_json(_market_state_json())
    index_state = stock_state.model_copy(
        update={
            "trend_regime": "descending",
            "momentum_regime": "negative",
            "liquidity_regime": "normal",
            "structure_quality": "breakdown_attempt",
            "trend_direction_score": -0.35,
            "trend_strength": 0.5,
            "momentum_score_value": -0.25,
            "risk_pressure_score": 0.65,
            "state_summary": "Index context has deteriorating structure.",
        }
    )

    strategy = policy_from_market_state(
        stock_state,
        _anchors(),
        holdings_info={},
        constraints={"bearish_volume_divergence": False},
        volume_regime="normal",
        market_context_state=index_state,
        market_context_ticker="^GSPC",
    )

    assert strategy.action == "BUY"
    assert 0.0 < strategy.entry.size_pct < 60.0
    assert "continuous_multiplier" in strategy.rationale_summary
    assert "bearish" not in strategy.rationale_summary


def test_early_bull_reversal_uses_existing_trend_market_entry_modifier():
    state = MarketState.model_validate_json(_market_state_json()).model_copy(
        update={
            "trend_strength": 0.45,
            "momentum_regime": "neutral",
            "liquidity_regime": "volume_expansion",
            "structure_quality": "fragmented",
            "trend_direction_score": 0.35,
            "momentum_score_value": 0.15,
        }
    )

    strategy = policy_from_market_state(
        state,
        _anchors(),
        holdings_info={},
        constraints={"bearish_volume_divergence": False},
        volume_regime="expanding",
    )

    assert state.regime == "weak_uptrend"
    assert state.market_phase == "early_bull_reversal"
    assert strategy.action == "BUY"
    assert strategy.entry.price is None
    assert strategy.entry.size_pct > 0


def test_weak_uptrend_soft_volume_caps_pullback_add():
    state = MarketState.model_validate_json(_market_state_json()).model_copy(
        update={
            "trend_strength": 0.45,
            "momentum_regime": "mean_reverting",
            "liquidity_regime": "normal",
            "structure_quality": "coherent",
            "trend_direction_score": 0.35,
            "momentum_score_value": 0.05,
        }
    )

    strategy = policy_from_market_state(
        state,
        _anchors(),
        holdings_info={"quantity": 100, "avg_buy_price": 450.0},
        constraints={"bearish_volume_divergence": False},
        volume_regime="soft",
    )

    assert state.regime == "weak_uptrend"
    assert state.market_phase == "bull_pullback"
    assert strategy.action == "BUY"
    assert strategy.add_position.size_pct == 15.0
    assert "weak uptrend with soft volume" in strategy.rationale_summary
