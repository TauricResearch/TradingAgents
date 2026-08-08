"""Unit tests for review-date parsing, category sizing, and volatility scaling."""

import pytest

from app.services.broker_rules import (
    REVIEW_DEFAULT_DAYS,
    REVIEW_MAX_DAYS,
    REVIEW_MIN_DAYS,
    buy_quantity,
    parse_review_days,
)
from app.services.volatility import default_stop_pct, event_threshold_pct


class TestParseReviewDays:
    def test_parses_pm_output(self):
        text = "**Time Horizon**: 3-6 months\n\n**Next Review**: 10 days"
        assert parse_review_days(text) == 10

    def test_clamps_low_and_high(self):
        assert parse_review_days("**Next Review**: 1 day") == REVIEW_MIN_DAYS
        assert parse_review_days("**Next Review**: 45 days") == REVIEW_MAX_DAYS

    def test_default_when_absent(self):
        assert parse_review_days("**Rating**: Hold") == REVIEW_DEFAULT_DAYS
        assert parse_review_days(None) == REVIEW_DEFAULT_DAYS


class TestCategorySizing:
    def test_core_buy_is_double_satellite_buy(self):
        core = buy_quantity("Buy", 10_000, 10_000, 100.0, 1.0, category="core")
        satellite = buy_quantity("Buy", 10_000, 10_000, 100.0, 1.0, category="satellite")
        assert core == pytest.approx(10.0)      # 10% of equity
        assert satellite == pytest.approx(5.0)  # 5% of equity

    def test_unknown_category_sizes_like_satellite(self):
        unknown = buy_quantity("Buy", 10_000, 10_000, 100.0, 1.0, category="whatever")
        assert unknown == pytest.approx(5.0)


class TestReviewPriority:
    def test_actionability_order(self):
        from app.services.pipeline import review_priority

        order = ["Buy", "Overweight", "Hold", "Underweight", "Sell", None]
        priorities = [review_priority(r) for r in order]
        assert priorities == sorted(priorities), "priority must decrease down the rating scale"
        assert review_priority("Buy") < review_priority("Hold")
        assert review_priority("Hold") < review_priority("Underweight")
        assert review_priority("Underweight") < review_priority("Sell")
        assert review_priority(None) > review_priority("Sell")


class TestVolatilityScaling:
    def test_stable_megacap_gets_floor_stop(self):
        # MSFT-like: ~0.9% daily -> 2.25% raw -> floored at 5%
        assert default_stop_pct(0.9) == 5.0

    def test_volatile_name_gets_wider_stop(self):
        # NVDA-like: ~2.8% daily -> 7% stop
        assert default_stop_pct(2.8) == pytest.approx(7.0)

    def test_biotech_hits_ceiling(self):
        assert default_stop_pct(6.0) == 12.0

    def test_unknown_volatility_is_conservative(self):
        assert default_stop_pct(None) == 10.0

    def test_event_thresholds_scale_and_clamp(self):
        assert event_threshold_pct(0.5) == 3.0    # floor
        assert event_threshold_pct(2.0) == pytest.approx(6.0)
        assert event_threshold_pct(9.0) == 10.0   # ceiling
        assert event_threshold_pct(None) == 5.0


class TestBudgetIsSizedForData:
    """The caps exist as a bug guard now, not as a quota throttle.

    Every limit in this system was originally sized around Ollama's weekly cap,
    which no longer applies. The binding constraint is the opposite: August's
    verdict was unprovable at an effective sample size of 3.19, so an unused
    slot costs an observation that cannot be recovered later.
    """

    def test_heartbeat_backfills_the_whole_slot(self):
        """P5 took exactly one ticker, so slots ran short whenever few were due."""
        import inspect

        from app.services import pipeline

        source = inspect.getsource(pipeline._select_candidates)
        assert "take(stalest)" in source, (
            "the heartbeat must backfill to batch_size; take(stalest[:1]) leaves "
            "the slot short every time fewer tickers are due than requested"
        )

    def test_heartbeat_reserve_is_not_restrictive(self):
        """The 0.7 gate switched the backfill off for a third of the week."""
        import inspect

        from app.services import pipeline

        source = inspect.getsource(pipeline._select_candidates)
        assert "< 0.9" in source, (
            "the heartbeat reserve should keep a small buffer for late-week "
            "position reviews, not idle the scheduler once 70% is spent"
        )

    def test_weekly_budget_exceeds_the_schedule(self):
        """The cap must not bind before the slots do, or runs get silently dropped."""
        from app.core.config import get_settings

        settings = get_settings()
        # 6 slots x 4 tickers x 5 weekdays = 120 potential weekday runs.
        assert settings.assistant_weekly_run_budget >= 120, (
            "weekly budget must cover the configured schedule, else the guard "
            "becomes a throttle and slots fail late in the week"
        )
        assert settings.assistant_daily_run_budget >= 24

    def test_screener_can_react_within_days(self):
        """At 1 add/day against a 21-day expiry the watchlist barely moved."""
        from app.core.config import get_settings

        settings = get_settings()
        assert settings.screener_max_adds >= 3
        assert settings.screener_satellite_cap >= 20, (
            "effective sample size comes from DISTINCT names; repeat looks at "
            "the same ticker are correlated observations"
        )
