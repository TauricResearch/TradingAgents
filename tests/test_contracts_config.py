"""Contract tests: ProConfig safety guarantees and legacy-config bridge."""

import pytest
from pydantic import ValidationError

from tradingagents.contracts import (
    AgentTeam,
    AssetClass,
    ModelRouting,
    ProConfig,
    RiskLimits,
    TradingMode,
)


def test_defaults_are_safe():
    config = ProConfig(asset=AssetClass.GOLD)
    assert config.mode is TradingMode.PAPER
    assert config.live_trading_enabled is False
    assert config.require_human_approval is True


def test_default_symbol_derived_per_asset():
    assert ProConfig(asset=AssetClass.GOLD).symbol == "XAUUSD"
    assert ProConfig(asset=AssetClass.BITCOIN).symbol == "BTC-USD"
    assert ProConfig(asset=AssetClass.BITCOIN, symbol="BTCUSDT").symbol == "BTCUSDT"


def test_live_mode_requires_explicit_enable_flag():
    with pytest.raises(ValidationError, match="live_trading_enabled"):
        ProConfig(asset=AssetClass.BITCOIN, mode=TradingMode.LIVE)


def test_live_mode_cannot_disable_human_approval():
    with pytest.raises(ValidationError, match="human-approval"):
        ProConfig(
            asset=AssetClass.BITCOIN,
            mode=TradingMode.LIVE,
            live_trading_enabled=True,
            require_human_approval=False,
        )


def test_live_mode_valid_with_both_safeguards():
    config = ProConfig(
        asset=AssetClass.GOLD,
        mode=TradingMode.LIVE,
        live_trading_enabled=True,
    )
    assert config.mode is TradingMode.LIVE
    assert config.require_human_approval is True


def test_debate_rounds_hard_cap():
    with pytest.raises(ValidationError):
        ProConfig(asset=AssetClass.GOLD, max_debate_rounds=11)


def test_risk_limits_reject_zero_risk():
    with pytest.raises(ValidationError):
        RiskLimits(max_risk_per_trade_pct=0)


def test_model_routing_tiers_and_overrides():
    routing = ModelRouting(team_overrides={AgentTeam.RISK: "gpt-5.5"})
    assert routing.model_for(AgentTeam.TECHNICAL) == routing.quick_think_llm
    assert routing.model_for(AgentTeam.TECHNICAL, deep=True) == routing.deep_think_llm
    assert routing.model_for(AgentTeam.RISK) == "gpt-5.5"


def test_to_legacy_config_bridges_without_mutating_defaults():
    from tradingagents.default_config import DEFAULT_CONFIG

    before = dict(DEFAULT_CONFIG)
    config = ProConfig(
        asset=AssetClass.GOLD,
        max_debate_rounds=3,
        models=ModelRouting(llm_provider="anthropic", deep_think_llm="claude-fable-5"),
    )
    legacy = config.to_legacy_config()

    assert legacy["max_debate_rounds"] == 3
    assert legacy["llm_provider"] == "anthropic"
    assert legacy["deep_think_llm"] == "claude-fable-5"
    # untouched keys flow through from the base framework
    assert legacy["data_vendors"] == DEFAULT_CONFIG["data_vendors"]
    # and the shared module-level dict is not mutated
    assert dict(DEFAULT_CONFIG) == before


def test_config_round_trips_through_json():
    config = ProConfig(asset=AssetClass.BITCOIN, max_debate_rounds=2)
    restored = ProConfig.model_validate_json(config.model_dump_json())
    assert restored == config
