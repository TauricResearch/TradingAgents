from datetime import datetime, timedelta

import pandas as pd

from tradingagents.discovery.stock_discovery import (
    DiscoveryConfig,
    DISCOVERY_REGIONS,
    StockCandidate,
    discover_trending_stocks,
    symbols_for_regions,
)


def _history(closes, volumes):
    dates = [datetime(2026, 8, 1) + timedelta(days=index) for index in range(len(closes))]
    return pd.DataFrame({"Close": closes, "Volume": volumes}, index=dates)


def test_discovery_ranks_momentum_and_volume_candidate_first():
    histories = {
        "HOT.US": _history([100, 101, 102, 104, 108, 113], [100, 100, 105, 120, 180, 260]),
        "FLAT.US": _history([100, 100, 100, 100, 100, 100], [100] * 6),
    }

    candidates = discover_trending_stocks(
        symbols=list(histories),
        config=DiscoveryConfig(lookback_days=5, candidate_limit=2),
        history_loader=histories.__getitem__,
    )

    assert [candidate.symbol for candidate in candidates] == ["HOT.US", "FLAT.US"]
    assert candidates[0].score > candidates[1].score
    assert "momentum" in " ".join(candidates[0].reasons).lower()
    assert "volume" in " ".join(candidates[0].reasons).lower()


def test_discovery_filters_insufficient_data_and_limits_results():
    histories = {
        "SHORT.US": _history([100, 101], [100, 100]),
        "ONE.US": _history([100, 105, 110, 115, 120, 125], [100] * 6),
        "TWO.US": _history([100, 99, 98, 97, 96, 95], [100] * 6),
    }

    candidates = discover_trending_stocks(
        symbols=list(histories),
        config=DiscoveryConfig(lookback_days=5, candidate_limit=1),
        history_loader=histories.__getitem__,
    )

    assert len(candidates) == 1
    assert candidates[0].symbol == "ONE.US"


def test_candidate_is_typed_and_score_is_bounded():
    histories = {
        "A.US": _history([100, 110, 120, 130, 140, 150], [100, 100, 100, 100, 100, 100])
    }

    [candidate] = discover_trending_stocks(
        symbols=list(histories),
        config=DiscoveryConfig(lookback_days=5),
        history_loader=histories.__getitem__,
    )

    assert isinstance(candidate, StockCandidate)
    assert 0 <= candidate.score <= 100
    assert candidate.latest_price == 150


def test_discovery_config_can_limit_results():
    histories = {
        symbol: _history([100, 101, 102, 103, 104, 105], [100] * 6)
        for symbol in ("A.US", "B.US", "C.US")
    }

    candidates = discover_trending_stocks(
        symbols=list(histories),
        config=DiscoveryConfig(lookback_days=5, candidate_limit=2),
        history_loader=histories.__getitem__,
    )

    assert len(candidates) == 2


def test_symbols_for_regions_combines_selected_regions_without_duplicates():
    symbols = symbols_for_regions(["us", "europe"])

    assert symbols
    assert "AAPL" in symbols
    assert "SAP.DE" in symbols
    assert len(symbols) == len(set(symbols))


def test_discovery_regions_include_non_us_europe_markets():
    assert {"canada", "japan", "india", "australia"}.issubset(DISCOVERY_REGIONS)