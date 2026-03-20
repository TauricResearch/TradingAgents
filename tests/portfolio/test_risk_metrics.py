"""Tests for tradingagents/portfolio/risk_metrics.py.

Coverage:
- Happy-path: all metrics computed from sufficient data
- Sharpe / Sortino: correct annualisation, sign, edge cases
- VaR: 5th-percentile logic
- Max drawdown: correct peak-to-trough
- Beta: covariance / variance calculation
- Sector concentration: weighted from holdings_snapshot
- Insufficient data: returns None gracefully
- Single snapshot: n_days = 0, all None
- Type validation: raises TypeError for non-PortfolioSnapshot input

Run::

    pytest tests/portfolio/test_risk_metrics.py -v
"""

from __future__ import annotations

import math

import pytest

from tradingagents.portfolio.models import PortfolioSnapshot
from tradingagents.portfolio.risk_metrics import (
    _daily_returns,
    _mean,
    _percentile,
    _std,
    compute_risk_metrics,
)


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def make_snapshot(
    total_value: float,
    date: str = "2026-01-01",
    holdings: list[dict] | None = None,
    portfolio_id: str = "pid",
) -> PortfolioSnapshot:
    """Create a minimal PortfolioSnapshot for testing."""
    return PortfolioSnapshot(
        snapshot_id="snap-1",
        portfolio_id=portfolio_id,
        snapshot_date=date,
        total_value=total_value,
        cash=0.0,
        equity_value=total_value,
        num_positions=len(holdings) if holdings else 0,
        holdings_snapshot=holdings or [],
    )


def nav_snapshots(nav_values: list[float]) -> list[PortfolioSnapshot]:
    """Build a list of snapshots from NAV values, one per day."""
    return [
        make_snapshot(v, date=f"2026-01-{i + 1:02d}")
        for i, v in enumerate(nav_values)
    ]


# ---------------------------------------------------------------------------
# Internal helper tests
# ---------------------------------------------------------------------------


class TestDailyReturns:
    def test_single_step(self):
        assert _daily_returns([100.0, 110.0]) == pytest.approx([0.1])

    def test_multi_step(self):
        r = _daily_returns([100.0, 110.0, 99.0])
        assert r[0] == pytest.approx(0.1)
        assert r[1] == pytest.approx((99.0 - 110.0) / 110.0)

    def test_zero_previous_returns_zero(self):
        r = _daily_returns([0.0, 100.0])
        assert r == [0.0]

    def test_empty_list(self):
        assert _daily_returns([]) == []

    def test_one_element(self):
        assert _daily_returns([100.0]) == []


class TestMean:
    def test_basic(self):
        assert _mean([1.0, 2.0, 3.0]) == pytest.approx(2.0)

    def test_single(self):
        assert _mean([5.0]) == pytest.approx(5.0)

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="empty"):
            _mean([])


class TestStd:
    def test_sample_std(self):
        # [1, 2, 3] sample std = sqrt(1) = 1
        assert _std([1.0, 2.0, 3.0]) == pytest.approx(1.0)

    def test_zero_variance(self):
        assert _std([5.0, 5.0, 5.0]) == pytest.approx(0.0)

    def test_insufficient_data_returns_zero(self):
        assert _std([1.0], ddof=1) == 0.0


class TestPercentile:
    def test_median(self):
        assert _percentile([1.0, 2.0, 3.0, 4.0, 5.0], 50) == pytest.approx(3.0)

    def test_5th_percentile_all_equal(self):
        assert _percentile([0.01] * 10, 5) == pytest.approx(0.01)

    def test_0th_percentile_is_min(self):
        assert _percentile([3.0, 1.0, 2.0], 0) == pytest.approx(1.0)

    def test_100th_percentile_is_max(self):
        assert _percentile([3.0, 1.0, 2.0], 100) == pytest.approx(3.0)

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            _percentile([], 50)


# ---------------------------------------------------------------------------
# compute_risk_metrics — type validation
# ---------------------------------------------------------------------------


class TestTypeValidation:
    def test_non_snapshot_raises_type_error(self):
        with pytest.raises(TypeError, match="PortfolioSnapshot"):
            compute_risk_metrics([{"total_value": 100.0}])  # type: ignore[list-item]

    def test_mixed_list_raises(self):
        snap = make_snapshot(100.0)
        with pytest.raises(TypeError):
            compute_risk_metrics([snap, "not-a-snapshot"])  # type: ignore[list-item]


# ---------------------------------------------------------------------------
# compute_risk_metrics — insufficient data
# ---------------------------------------------------------------------------


class TestInsufficientData:
    def test_empty_list(self):
        result = compute_risk_metrics([])
        assert result["sharpe"] is None
        assert result["sortino"] is None
        assert result["var_95"] is None
        assert result["max_drawdown"] is None
        assert result["beta"] is None
        assert result["sector_concentration"] == {}
        assert result["return_stats"]["n_days"] == 0

    def test_single_snapshot(self):
        result = compute_risk_metrics([make_snapshot(100_000.0)])
        assert result["sharpe"] is None
        assert result["sortino"] is None
        assert result["var_95"] is None
        assert result["max_drawdown"] is None
        assert result["return_stats"]["n_days"] == 0


# ---------------------------------------------------------------------------
# compute_risk_metrics — Sharpe ratio
# ---------------------------------------------------------------------------


class TestSharpe:
    def test_zero_std_returns_none(self):
        # All identical NAV → zero std → Sharpe cannot be computed
        snaps = nav_snapshots([100.0, 100.0, 100.0, 100.0])
        result = compute_risk_metrics(snaps)
        assert result["sharpe"] is None

    def test_positive_trend_positive_sharpe(self):
        # Uniformly rising NAV → positive mean return, positive Sharpe
        nav = [100.0 * (1.001 ** i) for i in range(30)]
        snaps = nav_snapshots(nav)
        result = compute_risk_metrics(snaps)
        assert result["sharpe"] is not None
        assert result["sharpe"] > 0.0

    def test_negative_trend_negative_sharpe(self):
        nav = [100.0 * (0.999 ** i) for i in range(30)]
        snaps = nav_snapshots(nav)
        result = compute_risk_metrics(snaps)
        assert result["sharpe"] is not None
        assert result["sharpe"] < 0.0

    def test_annualisation_factor(self):
        # Manually verify: r = [0.01, 0.01, -0.005]
        # mean = 0.005, std = std([0.01, 0.01, -0.005], ddof=1)
        # sharpe = mean / std * sqrt(252)
        returns = [0.01, 0.01, -0.005]
        mu = sum(returns) / len(returns)
        variance = sum((r - mu) ** 2 for r in returns) / (len(returns) - 1)
        sigma = math.sqrt(variance)
        expected = mu / sigma * math.sqrt(252)

        # Build snapshots that produce exactly these returns
        navs = [100.0]
        for r in returns:
            navs.append(navs[-1] * (1 + r))
        snaps = nav_snapshots(navs)
        result = compute_risk_metrics(snaps)
        assert result["sharpe"] == pytest.approx(expected, rel=1e-4)


# ---------------------------------------------------------------------------
# compute_risk_metrics — Sortino ratio
# ---------------------------------------------------------------------------


class TestSortino:
    def test_no_downside_returns_none(self):
        # All positive returns → no downside → Sortino = None
        nav = [100.0, 101.0, 102.5, 104.0, 106.0]
        snaps = nav_snapshots(nav)
        result = compute_risk_metrics(snaps)
        # No negative returns in this series → sortino is None
        assert result["sortino"] is None

    def test_mixed_returns_yields_sortino(self):
        # Volatile up/down series
        nav = [100.0, 105.0, 98.0, 103.0, 101.0, 107.0, 99.0, 104.0]
        snaps = nav_snapshots(nav)
        result = compute_risk_metrics(snaps)
        # Should compute when there are downside returns
        assert result["sortino"] is not None

    def test_sortino_greater_than_sharpe_for_skewed_up_distribution(self):
        # Many small up returns, few large down returns
        # In a right-skewed return series, Sortino > Sharpe
        nav = [100.0]
        for _ in range(25):
            nav.append(nav[-1] * 1.003)   # small daily gain
        # Add a few moderate losses
        for _ in range(5):
            nav.append(nav[-1] * 0.988)
        snaps = nav_snapshots(nav)
        result = compute_risk_metrics(snaps)
        if result["sharpe"] is not None and result["sortino"] is not None:
            assert result["sortino"] > result["sharpe"]


# ---------------------------------------------------------------------------
# compute_risk_metrics — VaR
# ---------------------------------------------------------------------------


class TestVaR:
    def test_insufficient_data_returns_none(self):
        snaps = nav_snapshots([100.0, 101.0, 102.0, 103.0])  # only 3 returns
        result = compute_risk_metrics(snaps)
        assert result["var_95"] is None

    def test_var_is_non_negative(self):
        nav = [100.0 + i * 0.5 + ((-1) ** i) * 3 for i in range(40)]
        snaps = nav_snapshots(nav)
        result = compute_risk_metrics(snaps)
        assert result["var_95"] is not None
        assert result["var_95"] >= 0.0

    def test_var_near_zero_for_stable_portfolio(self):
        # Very low volatility → VaR close to 0
        nav = [100_000.0 + i * 10 for i in range(30)]
        snaps = nav_snapshots(nav)
        result = compute_risk_metrics(snaps)
        # Returns are essentially constant positive → VaR ≈ 0
        assert result["var_95"] is not None
        assert result["var_95"] < 0.001


# ---------------------------------------------------------------------------
# compute_risk_metrics — Max drawdown
# ---------------------------------------------------------------------------


class TestMaxDrawdown:
    def test_no_drawdown(self):
        # Monotonically increasing NAV
        nav = [100.0 + i for i in range(10)]
        snaps = nav_snapshots(nav)
        result = compute_risk_metrics(snaps)
        assert result["max_drawdown"] == pytest.approx(0.0)

    def test_simple_drawdown(self):
        # Peak=200, trough=100 → drawdown = (100-200)/200 = -0.5
        nav = [100.0, 150.0, 200.0, 150.0, 100.0]
        snaps = nav_snapshots(nav)
        result = compute_risk_metrics(snaps)
        assert result["max_drawdown"] == pytest.approx(-0.5, rel=1e-4)

    def test_recovery_still_records_worst(self):
        # Goes down then recovers
        nav = [100.0, 80.0, 90.0, 110.0]
        snaps = nav_snapshots(nav)
        result = compute_risk_metrics(snaps)
        # Worst trough: 80/100 - 1 = -0.2
        assert result["max_drawdown"] == pytest.approx(-0.2, rel=1e-4)

    def test_two_snapshots(self):
        snaps = nav_snapshots([100.0, 90.0])
        result = compute_risk_metrics(snaps)
        assert result["max_drawdown"] == pytest.approx(-0.1, rel=1e-4)


# ---------------------------------------------------------------------------
# compute_risk_metrics — Beta
# ---------------------------------------------------------------------------


class TestBeta:
    def test_no_benchmark_returns_none(self):
        snaps = nav_snapshots([100.0, 102.0, 101.0, 103.0, 104.0])
        result = compute_risk_metrics(snaps, benchmark_returns=None)
        assert result["beta"] is None

    def test_empty_benchmark_returns_none(self):
        snaps = nav_snapshots([100.0, 102.0, 101.0, 103.0, 104.0])
        result = compute_risk_metrics(snaps, benchmark_returns=[])
        assert result["beta"] is None

    def test_perfect_correlation_beta_one(self):
        # Portfolio returns = benchmark returns → beta = 1
        nav = [100.0, 102.0, 101.0, 103.5, 105.0]
        snaps = nav_snapshots(nav)
        returns = [(nav[i] - nav[i - 1]) / nav[i - 1] for i in range(1, len(nav))]
        result = compute_risk_metrics(snaps, benchmark_returns=returns)
        assert result["beta"] == pytest.approx(1.0, rel=1e-4)

    def test_double_beta(self):
        # Portfolio returns = 2 × benchmark → beta ≈ 2
        bench = [0.01, -0.005, 0.008, 0.002, -0.003]
        port_returns = [r * 2 for r in bench]
        # Build NAV from port_returns
        nav = [100.0]
        for r in port_returns:
            nav.append(nav[-1] * (1 + r))
        snaps = nav_snapshots(nav)
        result = compute_risk_metrics(snaps, benchmark_returns=bench)
        assert result["beta"] == pytest.approx(2.0, rel=1e-3)

    def test_zero_variance_benchmark_returns_none(self):
        bench = [0.0, 0.0, 0.0, 0.0]
        snaps = nav_snapshots([100.0, 101.0, 102.0, 103.0, 104.0])
        result = compute_risk_metrics(snaps, benchmark_returns=bench)
        assert result["beta"] is None


# ---------------------------------------------------------------------------
# compute_risk_metrics — Sector concentration
# ---------------------------------------------------------------------------


class TestSectorConcentration:
    def test_empty_holdings(self):
        snap = make_snapshot(100_000.0, holdings=[])
        result = compute_risk_metrics([snap, make_snapshot(105_000.0)])
        assert result["sector_concentration"] == {}

    def test_single_sector(self):
        holdings = [
            {"ticker": "AAPL", "shares": 100, "avg_cost": 150.0, "sector": "Technology"},
        ]
        # Sector concentration reads from the LAST snapshot
        last_snap = make_snapshot(100_000.0, holdings=holdings)
        result = compute_risk_metrics([make_snapshot(98_000.0), last_snap])
        # Technology weight = (100 * 150) / 100_000 * 100 = 15 %
        assert "Technology" in result["sector_concentration"]
        assert result["sector_concentration"]["Technology"] == pytest.approx(15.0, rel=0.01)

    def test_multiple_sectors_sum_to_equity_fraction(self):
        holdings = [
            {"ticker": "AAPL", "shares": 100, "avg_cost": 100.0, "sector": "Technology"},
            {"ticker": "JPM",  "shares": 50,  "avg_cost": 200.0, "sector": "Financials"},
        ]
        total_nav = 100_000.0
        last_snap = make_snapshot(total_nav, holdings=holdings)
        result = compute_risk_metrics([make_snapshot(99_000.0), last_snap])
        conc = result["sector_concentration"]
        assert "Technology" in conc
        assert "Financials" in conc
        # Technology: 10_000 / 100_000 = 10 %
        assert conc["Technology"] == pytest.approx(10.0, rel=0.01)
        # Financials: 10_000 / 100_000 = 10 %
        assert conc["Financials"] == pytest.approx(10.0, rel=0.01)

    def test_uses_current_value_when_available(self):
        holdings = [
            {
                "ticker": "AAPL",
                "shares": 100,
                "avg_cost": 100.0,
                "current_value": 20_000.0,  # current, not cost
                "sector": "Technology",
            },
        ]
        last_snap = make_snapshot(100_000.0, holdings=holdings)
        result = compute_risk_metrics([make_snapshot(98_000.0), last_snap])
        # current_value preferred: 20_000 / 100_000 * 100 = 20 %
        assert result["sector_concentration"]["Technology"] == pytest.approx(20.0, rel=0.01)

    def test_missing_sector_defaults_to_unknown(self):
        holdings = [
            {"ticker": "AAPL", "shares": 100, "avg_cost": 100.0},  # no sector key
        ]
        last_snap = make_snapshot(100_000.0, holdings=holdings)
        result = compute_risk_metrics([make_snapshot(100_000.0), last_snap])
        assert "Unknown" in result["sector_concentration"]


# ---------------------------------------------------------------------------
# compute_risk_metrics — return_stats
# ---------------------------------------------------------------------------


class TestReturnStats:
    def test_n_days_matches_returns_length(self):
        snaps = nav_snapshots([100.0, 102.0, 101.0])
        result = compute_risk_metrics(snaps)
        assert result["return_stats"]["n_days"] == 2

    def test_mean_and_std_present(self):
        snaps = nav_snapshots([100.0, 102.0, 101.0, 103.5])
        result = compute_risk_metrics(snaps)
        stats = result["return_stats"]
        assert stats["mean_daily"] is not None
        assert stats["std_daily"] is not None

    def test_empty_stats(self):
        result = compute_risk_metrics([])
        stats = result["return_stats"]
        assert stats["mean_daily"] is None
        assert stats["std_daily"] is None
        assert stats["n_days"] == 0


# ---------------------------------------------------------------------------
# compute_risk_metrics — full integration scenario
# ---------------------------------------------------------------------------


class TestFullScenario:
    def test_90_day_realistic_portfolio(self):
        """90-day NAV series with realistic up/down patterns."""
        import random

        random.seed(42)
        nav = [100_000.0]
        for _ in range(89):
            daily_r = random.gauss(0.0005, 0.01)  # ~12.5 % annual, 10 % vol
            nav.append(nav[-1] * (1 + daily_r))

        bench_returns = [random.gauss(0.0004, 0.009) for _ in range(89)]

        holdings = [
            {"ticker": "AAPL", "shares": 100, "avg_cost": 175.0, "sector": "Technology"},
            {"ticker": "JPM",  "shares": 50,  "avg_cost": 200.0, "sector": "Financials"},
        ]
        snaps = []
        for i, v in enumerate(nav):
            h = holdings if i == len(nav) - 1 else []
            snaps.append(
                PortfolioSnapshot(
                    snapshot_id=f"snap-{i}",
                    portfolio_id="pid",
                    snapshot_date=f"2026-01-{i + 1:02d}" if i < 31 else f"2026-02-{i - 30:02d}" if i < 59 else f"2026-03-{i - 58:02d}",
                    total_value=v,
                    cash=0.0,
                    equity_value=v,
                    num_positions=2,
                    holdings_snapshot=h,
                )
            )

        result = compute_risk_metrics(snaps, benchmark_returns=bench_returns)

        # All key metrics should be present
        assert result["sharpe"] is not None
        assert result["sortino"] is not None
        assert result["var_95"] is not None
        assert result["max_drawdown"] is not None
        assert result["beta"] is not None
        assert result["return_stats"]["n_days"] == 89

        # Sector concentration from last snapshot
        assert "Technology" in result["sector_concentration"]
        assert "Financials" in result["sector_concentration"]

        # Sanity bounds
        assert -10.0 < result["sharpe"] < 10.0
        assert result["max_drawdown"] <= 0.0
        assert result["var_95"] >= 0.0
        assert result["beta"] > 0.0  # should be positive for realistic market data
