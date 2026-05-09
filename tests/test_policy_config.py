import argparse

from back_test.policy_config import (
    PortfolioStatePolicyConfig,
    add_portfolio_state_policy_args,
    coerce_portfolio_state_policy_config,
    portfolio_state_policy_config_from_args,
)


def test_policy_config_defaults_match_simplified_cli_defaults():
    parser = argparse.ArgumentParser()
    add_portfolio_state_policy_args(parser)
    args = parser.parse_args([])

    config = coerce_portfolio_state_policy_config(
        portfolio_state_policy_config_from_args(args)
    )
    defaults = PortfolioStatePolicyConfig()

    assert config == defaults


def test_simplified_policy_args_expand_to_internal_config():
    parser = argparse.ArgumentParser()
    add_portfolio_state_policy_args(parser)
    args = parser.parse_args(
        [
            "--ps-trade-frequency", "high",
            "--ps-add-max", "18",
            "--ps-max-weight", "0.8",
        ]
    )

    config = portfolio_state_policy_config_from_args(args)

    assert config["min_trade_weight"] == 0.01
    assert config["default_add_max_pct"] == 18
    assert config["pullback_entry_add_max_pct"] == 18
    assert config["weak_uptrend_soft_volume_add_max_pct"] == 18
    assert config["max_target_weight"] == 0.8


def test_legacy_policy_args_still_parse_but_are_hidden_from_help():
    parser = argparse.ArgumentParser()
    add_portfolio_state_policy_args(parser)
    args = parser.parse_args(["--ps-weak-cap", "0.52", "--ps-profile", "aggressive"])

    config = portfolio_state_policy_config_from_args(args)
    help_text = parser.format_help()

    assert config["weak_uptrend_cap"] == 0.52
    assert config["strong_uptrend_cap"] == 1.00
    assert "--ps-trade-frequency" in help_text
    assert "--ps-profile" not in help_text
    assert "--ps-weak-cap" not in help_text
