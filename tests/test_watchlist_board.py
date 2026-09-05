from datetime import date, datetime, timezone

from tradingagents.research_platform.agent_contracts import (
    TradeDirection,
    TradeHorizon,
    TradeSignal,
)
from tradingagents.research_platform.artifact_store import JsonArtifactStore
from tradingagents.research_platform.data_contracts import DataProvenance, PriceBar
from tradingagents.research_platform.research_report import ResearchReportBundle
from tradingagents.research_platform.run_archive import JsonResearchRunArchive
from tradingagents.research_platform.watchlist import JsonWatchlistStore
from tradingagents.research_platform.watchlist_board import build_watchlist_board


def _provenance() -> DataProvenance:
    return DataProvenance(
        provider="fixture",
        as_of_date=date(2026, 1, 5),
        retrieved_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
    )


def test_watchlist_board_combines_cached_price_research_and_health(tmp_path):
    store = JsonArtifactStore(tmp_path)
    watchlist = JsonWatchlistStore(tmp_path)
    watchlist.add("NVDA")
    watchlist.add("MSFT")
    store.save_price_bars(
        [
            PriceBar(
                symbol="NVDA",
                date=date(2026, 1, 5),
                open=100,
                high=105,
                low=99,
                close=103,
                volume=100,
                currency="USD",
                provenance=_provenance(),
            )
        ]
    )
    JsonResearchRunArchive(tmp_path).save_bundle(
        ResearchReportBundle(
            symbol="NVDA",
            as_of_date=datetime(2026, 1, 5, tzinfo=timezone.utc),
            generated_at=datetime(2026, 1, 5, 12, tzinfo=timezone.utc),
            signal=TradeSignal(
                symbol="NVDA",
                as_of_date=date(2026, 1, 5),
                direction=TradeDirection.BUY,
                horizon=TradeHorizon.MEDIUM,
                confidence=0.8,
                rationale="Fixture decision.",
            ),
        )
    )

    board = build_watchlist_board(store, watchlist)
    msft, nvda = board["items"]

    assert board["total"] == 2
    assert board["researched"] == 1
    assert msft["symbol"] == "MSFT"
    assert msft["data_status"] == "missing"
    assert nvda["symbol"] == "NVDA"
    assert nvda["last_close"] == 103
    assert nvda["latest_research_at"] == "2026-01-05T12:00:00+00:00"
    assert nvda["decision"] == "buy"
    assert nvda["data_status"] == "missing"
