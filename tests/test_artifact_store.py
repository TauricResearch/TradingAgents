from datetime import date, datetime, timezone

from tradingagents.research_platform.artifact_store import JsonArtifactStore
from tradingagents.research_platform.data_contracts import (
    DataProvenance,
    FundamentalSnapshot,
    NewsItem,
    PriceBar,
)


def _provenance(as_of_date: date) -> DataProvenance:
    return DataProvenance(
        provider="fixture",
        as_of_date=as_of_date,
        retrieved_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
        source="fixture",
        vendor_symbol="NVDA",
    )


def test_json_artifact_store_round_trips_price_bars(tmp_path):
    store = JsonArtifactStore(tmp_path)
    store.save_price_bars(
        [
            PriceBar(
                symbol="NVDA",
                date=date(2026, 1, 2),
                open=100,
                high=105,
                low=99,
                close=104,
                adjusted_close=103.5,
                volume=1000,
                provenance=_provenance(date(2026, 1, 2)),
            ),
            PriceBar(
                symbol="NVDA",
                date=date(2026, 1, 3),
                open=104,
                high=106,
                low=103,
                close=105,
                volume=2000,
                provenance=_provenance(date(2026, 1, 3)),
            ),
        ]
    )

    bars = store.load_price_bars(
        "NVDA",
        date(2026, 1, 1),
        date(2026, 1, 3),
        as_of_date=date(2026, 1, 2),
    )

    assert len(bars) == 1
    assert bars[0].date == date(2026, 1, 2)
    assert bars[0].close == 104


def test_json_artifact_store_merges_duplicate_price_keys(tmp_path):
    store = JsonArtifactStore(tmp_path)
    first = PriceBar(
        symbol="NVDA",
        date=date(2026, 1, 2),
        open=100,
        high=105,
        low=99,
        close=104,
        provenance=_provenance(date(2026, 1, 2)),
    )
    replacement = PriceBar(
        symbol="NVDA",
        date=date(2026, 1, 2),
        open=100,
        high=106,
        low=99,
        close=105,
        provenance=_provenance(date(2026, 1, 2)),
    )

    store.save_price_bars([first])
    store.save_price_bars([replacement])

    bars = store.load_price_bars("NVDA", date(2026, 1, 1), date(2026, 1, 3))
    assert len(bars) == 1
    assert bars[0].close == 105



def test_json_artifact_store_collapses_point_in_time_price_versions_by_trade_date(tmp_path):
    store = JsonArtifactStore(tmp_path)
    adjusted = PriceBar(
        symbol="NVDA",
        date=date(2026, 1, 2),
        open=100,
        high=105,
        low=99,
        close=104,
        adjusted_close=102,
        adjustment_factor=1.5,
        adjustment_method="forward_adjusted",
        provenance=_provenance(date(2026, 1, 2)),
    )
    later_raw = PriceBar(
        symbol="NVDA",
        date=date(2026, 1, 2),
        open=100,
        high=106,
        low=99,
        close=105,
        provenance=_provenance(date(2026, 1, 3)),
    )

    store.save_price_bars([adjusted, later_raw])

    bars = store.load_price_bars("NVDA", date(2026, 1, 1), date(2026, 1, 3))
    assert len(bars) == 1
    assert bars[0].adjusted_close == 102
    assert bars[0].adjustment_method == "forward_adjusted"


def test_json_artifact_store_round_trips_fundamentals(tmp_path):
    store = JsonArtifactStore(tmp_path)
    store.save_fundamentals(
        [
            FundamentalSnapshot(
                symbol="NVDA",
                period_end=date(2026, 1, 5),
                fiscal_period="snapshot",
                currency="USD",
                metrics={"market_cap": 3000000000000, "pe_ratio_ttm": 42.5},
                provenance=_provenance(date(2026, 1, 5)),
            )
        ]
    )

    snapshots = store.load_fundamentals("NVDA", as_of_date=date(2026, 1, 5))

    assert len(snapshots) == 1
    assert snapshots[0].metrics["market_cap"] == 3000000000000


def test_json_artifact_store_round_trips_news(tmp_path):
    store = JsonArtifactStore(tmp_path)
    store.save_news(
        [
            NewsItem(
                symbol="NVDA",
                title="Nvidia launches platform",
                published_at=datetime(2026, 1, 4, 15, 30, tzinfo=timezone.utc),
                as_of_date=date(2026, 1, 4),
                provider="Example News",
                url="https://example.com/nvda",
                summary="Summary.",
                source_id="news-1",
            ),
            NewsItem(
                symbol="NVDA",
                title="Future article",
                published_at=datetime(2026, 1, 6, 15, 30, tzinfo=timezone.utc),
                as_of_date=date(2026, 1, 6),
                provider="Example News",
                source_id="news-2",
            ),
        ]
    )

    items = store.load_news(
        "NVDA",
        date(2026, 1, 1),
        date(2026, 1, 6),
        as_of_date=date(2026, 1, 5),
    )

    assert len(items) == 1
    assert items[0].source_id == "news-1"


def test_json_artifact_store_keeps_daily_and_financial_snapshots_for_same_period(tmp_path):
    store = JsonArtifactStore(tmp_path)
    daily = FundamentalSnapshot(
        symbol="600519",
        period_end=date(2026, 3, 31),
        fiscal_period="daily_snapshot",
        metrics={"pe_ratio_ttm": 20.0},
        provenance=_provenance(date(2026, 4, 1)),
    )
    financial = FundamentalSnapshot(
        symbol="600519",
        period_end=date(2026, 3, 31),
        fiscal_period="financial_report_2026-03-31",
        metrics={"reported_net_income": 100.0},
        provenance=_provenance(date(2026, 4, 1)),
    )

    store.save_fundamentals([daily, financial])

    snapshots = store.load_fundamentals("600519")
    assert {item.fiscal_period for item in snapshots} == {
        "daily_snapshot",
        "financial_report_2026-03-31",
    }
