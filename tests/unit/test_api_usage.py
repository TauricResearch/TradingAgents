"""Tests for tradingagents/api_usage.py — API consumption estimation."""

import pytest

from tradingagents.api_usage import (
    AV_FREE_DAILY_LIMIT,
    AV_PREMIUM_PER_MINUTE,
    UsageEstimate,
    VendorEstimate,
    estimate_analyze,
    estimate_pipeline,
    estimate_scan,
    format_av_assessment,
    format_estimate,
    format_vendor_breakdown,
)


# ──────────────────────────────────────────────────────────────────────────────
# VendorEstimate
# ──────────────────────────────────────────────────────────────────────────────


class TestVendorEstimate:
    def test_total(self):
        ve = VendorEstimate(yfinance=10, alpha_vantage=5, finnhub=2)
        assert ve.total == 17

    def test_default_zeros(self):
        ve = VendorEstimate()
        assert ve.total == 0


# ──────────────────────────────────────────────────────────────────────────────
# UsageEstimate
# ──────────────────────────────────────────────────────────────────────────────


class TestUsageEstimate:
    def test_av_fits_free_tier_true(self):
        est = UsageEstimate(
            command="test",
            description="test",
            vendor_calls=VendorEstimate(alpha_vantage=10),
        )
        assert est.av_fits_free_tier() is True

    def test_av_fits_free_tier_false(self):
        est = UsageEstimate(
            command="test",
            description="test",
            vendor_calls=VendorEstimate(alpha_vantage=100),
        )
        assert est.av_fits_free_tier() is False

    def test_av_daily_runs_free(self):
        est = UsageEstimate(
            command="test",
            description="test",
            vendor_calls=VendorEstimate(alpha_vantage=5),
        )
        assert est.av_daily_runs_free() == AV_FREE_DAILY_LIMIT // 5

    def test_av_daily_runs_free_zero_av(self):
        est = UsageEstimate(
            command="test",
            description="test",
            vendor_calls=VendorEstimate(alpha_vantage=0),
        )
        assert est.av_daily_runs_free() == -1  # unlimited


# ──────────────────────────────────────────────────────────────────────────────
# estimate_analyze — default config (yfinance primary)
# ──────────────────────────────────────────────────────────────────────────────


class TestEstimateAnalyze:
    def test_default_config_no_av_calls(self):
        """With default config (yfinance primary), AV calls should be 0."""
        est = estimate_analyze()
        assert est.vendor_calls.alpha_vantage == 0
        assert est.vendor_calls.yfinance > 0

    def test_all_analysts_nonzero_total(self):
        est = estimate_analyze(selected_analysts=["market", "news", "fundamentals", "social"])
        assert est.vendor_calls.total > 0

    def test_market_only(self):
        est = estimate_analyze(selected_analysts=["market"], num_indicators=4)
        # 1 stock data + 4 indicators = 5 calls
        assert est.vendor_calls.total >= 5

    def test_fundamentals_includes_insider(self):
        """Fundamentals analyst should include insider_transactions (Finnhub default)."""
        est = estimate_analyze(selected_analysts=["fundamentals"])
        # insider_transactions defaults to finnhub
        assert est.vendor_calls.finnhub >= 1

    def test_num_indicators_varies_total(self):
        est_low = estimate_analyze(selected_analysts=["market"], num_indicators=2)
        est_high = estimate_analyze(selected_analysts=["market"], num_indicators=8)
        assert est_high.vendor_calls.total > est_low.vendor_calls.total

    def test_av_config_counts_av_calls(self):
        """When AV is configured as primary, calls should show up under alpha_vantage."""
        av_config = {
            "data_vendors": {
                "core_stock_apis": "alpha_vantage",
                "technical_indicators": "alpha_vantage",
                "fundamental_data": "alpha_vantage",
                "news_data": "alpha_vantage",
                "scanner_data": "alpha_vantage",
                "calendar_data": "finnhub",
            },
            "tool_vendors": {
                "get_insider_transactions": "alpha_vantage",
            },
        }
        est = estimate_analyze(config=av_config, selected_analysts=["market", "fundamentals"])
        assert est.vendor_calls.alpha_vantage > 0
        assert est.vendor_calls.yfinance == 0

    def test_method_breakdown_has_entries(self):
        est = estimate_analyze(selected_analysts=["market"])
        assert len(est.method_breakdown) > 0

    def test_notes_populated(self):
        est = estimate_analyze()
        assert len(est.notes) > 0


# ──────────────────────────────────────────────────────────────────────────────
# estimate_scan — default config (yfinance primary)
# ──────────────────────────────────────────────────────────────────────────────


class TestEstimateScan:
    def test_default_config_uses_yfinance(self):
        est = estimate_scan()
        assert est.vendor_calls.yfinance > 0

    def test_finnhub_for_calendars(self):
        """Calendars should always use Finnhub."""
        est = estimate_scan()
        assert est.vendor_calls.finnhub >= 2  # earnings + economic calendar

    def test_scan_total_reasonable(self):
        est = estimate_scan()
        # Should be between 15-40 calls total
        assert 10 <= est.vendor_calls.total <= 50

    def test_notes_have_phases(self):
        est = estimate_scan()
        phase_notes = [n for n in est.notes if "Phase" in n]
        assert len(phase_notes) >= 3  # Phase 1A, 1B, 1C, 2, 3


# ──────────────────────────────────────────────────────────────────────────────
# estimate_pipeline
# ──────────────────────────────────────────────────────────────────────────────


class TestEstimatePipeline:
    def test_pipeline_larger_than_scan(self):
        scan_est = estimate_scan()
        pipe_est = estimate_pipeline(num_tickers=3)
        assert pipe_est.vendor_calls.total > scan_est.vendor_calls.total

    def test_pipeline_scales_with_tickers(self):
        est3 = estimate_pipeline(num_tickers=3)
        est7 = estimate_pipeline(num_tickers=7)
        assert est7.vendor_calls.total > est3.vendor_calls.total

    def test_pipeline_av_config(self):
        """Pipeline with AV config should report AV calls."""
        av_config = {
            "data_vendors": {
                "core_stock_apis": "alpha_vantage",
                "technical_indicators": "alpha_vantage",
                "fundamental_data": "alpha_vantage",
                "news_data": "alpha_vantage",
                "scanner_data": "alpha_vantage",
                "calendar_data": "finnhub",
            },
            "tool_vendors": {},
        }
        est = estimate_pipeline(config=av_config, num_tickers=5)
        assert est.vendor_calls.alpha_vantage > 0


# ──────────────────────────────────────────────────────────────────────────────
# format_estimate
# ──────────────────────────────────────────────────────────────────────────────


class TestFormatEstimate:
    def test_contains_vendor_counts(self):
        est = estimate_analyze()
        text = format_estimate(est)
        assert "yfinance" in text
        assert "Total:" in text

    def test_no_av_shows_not_needed(self):
        est = estimate_analyze()  # default config → no AV
        text = format_estimate(est)
        assert "NOT needed" in text

    def test_av_shows_assessment(self):
        av_config = {
            "data_vendors": {
                "core_stock_apis": "alpha_vantage",
                "technical_indicators": "alpha_vantage",
                "fundamental_data": "alpha_vantage",
                "news_data": "alpha_vantage",
                "scanner_data": "alpha_vantage",
                "calendar_data": "finnhub",
            },
            "tool_vendors": {},
        }
        est = estimate_analyze(config=av_config)
        text = format_estimate(est)
        assert "Alpha Vantage" in text


# ──────────────────────────────────────────────────────────────────────────────
# format_vendor_breakdown (actual run data)
# ──────────────────────────────────────────────────────────────────────────────


class TestFormatVendorBreakdown:
    def test_empty_summary(self):
        assert format_vendor_breakdown({}) == ""

    def test_yfinance_only(self):
        summary = {"vendors_used": {"yfinance": {"ok": 10, "fail": 0}}}
        text = format_vendor_breakdown(summary)
        assert "yfinance:10ok/0fail" in text

    def test_multiple_vendors(self):
        summary = {
            "vendors_used": {
                "yfinance": {"ok": 8, "fail": 1},
                "alpha_vantage": {"ok": 3, "fail": 0},
                "finnhub": {"ok": 2, "fail": 0},
            }
        }
        text = format_vendor_breakdown(summary)
        assert "yfinance:8ok/1fail" in text
        assert "AV:3ok/0fail" in text
        assert "Finnhub:2ok/0fail" in text


# ──────────────────────────────────────────────────────────────────────────────
# format_av_assessment (actual run data)
# ──────────────────────────────────────────────────────────────────────────────


class TestFormatAvAssessment:
    def test_no_av_used(self):
        summary = {"vendors_used": {"yfinance": {"ok": 10, "fail": 0}}}
        text = format_av_assessment(summary)
        assert "not used" in text

    def test_av_within_free(self):
        summary = {"vendors_used": {"alpha_vantage": {"ok": 5, "fail": 0}}}
        text = format_av_assessment(summary)
        assert "free tier" in text
        assert "5 calls" in text

    def test_av_exceeds_free(self):
        summary = {"vendors_used": {"alpha_vantage": {"ok": 30, "fail": 0}}}
        text = format_av_assessment(summary)
        assert "exceeds" in text
        assert "Premium" in text


# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────


class TestConstants:
    def test_av_free_daily_limit(self):
        assert AV_FREE_DAILY_LIMIT == 25

    def test_av_premium_per_minute(self):
        assert AV_PREMIUM_PER_MINUTE == 75
