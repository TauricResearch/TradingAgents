import pytest


class TestCalculateStopLoss:
    def test_calculate_stop_loss_default_multiplier(self):
        from tradingagents.agents.discovery.indicators.risk_reward import (
            calculate_stop_loss,
        )

        stop = calculate_stop_loss(price=100.0, atr=2.0, multiplier=1.5)
        assert stop == 97.0

    def test_calculate_stop_loss_custom_multiplier(self):
        from tradingagents.agents.discovery.indicators.risk_reward import (
            calculate_stop_loss,
        )

        stop = calculate_stop_loss(price=100.0, atr=2.0, multiplier=2.0)
        assert stop == 96.0

    def test_calculate_stop_loss_large_atr(self):
        from tradingagents.agents.discovery.indicators.risk_reward import (
            calculate_stop_loss,
        )

        stop = calculate_stop_loss(price=100.0, atr=10.0, multiplier=1.5)
        assert stop == 85.0


class TestCalculateRewardTarget:
    def test_calculate_reward_target(self):
        from tradingagents.agents.discovery.indicators.risk_reward import (
            calculate_reward_target,
        )

        target = calculate_reward_target(price=100.0, resistance=120.0)
        assert target == 120.0

    def test_calculate_reward_target_resistance_below_price(self):
        from tradingagents.agents.discovery.indicators.risk_reward import (
            calculate_reward_target,
        )

        target = calculate_reward_target(price=100.0, resistance=90.0)
        assert target == 90.0


class TestCalculateRiskRewardRatio:
    def test_calculate_rr_ratio_good_trade(self):
        from tradingagents.agents.discovery.indicators.risk_reward import (
            calculate_risk_reward_ratio,
        )

        rr = calculate_risk_reward_ratio(price=100.0, stop=95.0, target=115.0)
        assert rr == 3.0

    def test_calculate_rr_ratio_poor_trade(self):
        from tradingagents.agents.discovery.indicators.risk_reward import (
            calculate_risk_reward_ratio,
        )

        rr = calculate_risk_reward_ratio(price=100.0, stop=95.0, target=102.0)
        assert rr == pytest.approx(0.4, rel=0.01)

    def test_calculate_rr_ratio_stop_at_price_returns_zero(self):
        from tradingagents.agents.discovery.indicators.risk_reward import (
            calculate_risk_reward_ratio,
        )

        rr = calculate_risk_reward_ratio(price=100.0, stop=100.0, target=110.0)
        assert rr == 0.0

    def test_calculate_rr_ratio_target_below_price(self):
        from tradingagents.agents.discovery.indicators.risk_reward import (
            calculate_risk_reward_ratio,
        )

        rr = calculate_risk_reward_ratio(price=100.0, stop=95.0, target=98.0)
        assert rr < 0


class TestCalculateRiskRewardScore:
    def test_excellent_rr_ratio_high_score(self):
        from tradingagents.agents.discovery.indicators.risk_reward import (
            calculate_risk_reward_score,
        )

        score = calculate_risk_reward_score(rr_ratio=3.5)
        assert 0.9 <= score <= 1.0

    def test_good_rr_ratio_moderate_high_score(self):
        from tradingagents.agents.discovery.indicators.risk_reward import (
            calculate_risk_reward_score,
        )

        score = calculate_risk_reward_score(rr_ratio=2.5)
        assert 0.7 <= score <= 0.9

    def test_acceptable_rr_ratio_moderate_score(self):
        from tradingagents.agents.discovery.indicators.risk_reward import (
            calculate_risk_reward_score,
        )

        score = calculate_risk_reward_score(rr_ratio=1.5)
        assert 0.4 <= score <= 0.7

    def test_poor_rr_ratio_low_score(self):
        from tradingagents.agents.discovery.indicators.risk_reward import (
            calculate_risk_reward_score,
        )

        score = calculate_risk_reward_score(rr_ratio=0.5)
        assert 0.0 <= score <= 0.4

    def test_negative_rr_ratio_very_low_score(self):
        from tradingagents.agents.discovery.indicators.risk_reward import (
            calculate_risk_reward_score,
        )

        score = calculate_risk_reward_score(rr_ratio=-1.0)
        assert score == 0.0
