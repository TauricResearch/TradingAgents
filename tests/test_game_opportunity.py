from datetime import date, datetime, timedelta, timezone

from tradingagents.research_platform.artifact_store import JsonArtifactStore
from tradingagents.research_platform.data_contracts import (
    DataProvenance,
    FundamentalSnapshot,
    PriceBar,
)
from tradingagents.research_platform.game_approvals import (
    GameApprovalKind,
    GameApprovalRecord,
    JsonGameApprovalStore,
    make_approval_id,
)
from tradingagents.research_platform.game_opportunity import (
    GameOpportunityLevel,
    build_game_opportunity_board,
    build_game_opportunity_snapshot,
)


def _provenance(as_of: date) -> DataProvenance:
    return DataProvenance(
        provider="fixture",
        as_of_date=as_of,
        retrieved_at=datetime(2026, 7, 12, tzinfo=timezone.utc),
        source_url="https://example.com/data",
    )


def _seed_market_and_financials(
    store: JsonArtifactStore,
    symbol: str,
    *,
    reference_date: date,
    rising: bool,
    profit_yoy: float,
    cashflow: float,
) -> None:
    bars = []
    for offset in range(70):
        bar_date = reference_date - timedelta(days=69 - offset)
        close = 10 + offset * 0.1 if rising else 20 - offset * 0.1
        bars.append(
            PriceBar(
                symbol=symbol,
                date=bar_date,
                open=close,
                high=close,
                low=close,
                close=close,
                volume=1_000,
                provenance=_provenance(bar_date),
            )
        )
    store.save_price_bars(bars)
    store.save_fundamentals(
        [
            FundamentalSnapshot(
                symbol=symbol,
                period_end=date(2026, 3, 31),
                fiscal_period="financial_report_2026-03-31",
                metrics={
                    "net_profit_yoy_pct": profit_yoy,
                    "reported_operating_cashflow": cashflow,
                },
                provenance=_provenance(date(2026, 4, 30)),
            )
        ]
    )


def _approval(approved_on: date, number: str) -> GameApprovalRecord:
    kind = GameApprovalKind.DOMESTIC
    return GameApprovalRecord(
        approval_id=make_approval_id(kind, number, f"Game {number}"),
        kind=kind,
        game_name=f"Game {number}",
        publishing_entity="\u4e0a\u6d77\u6570\u9f99\u79d1\u6280\u6709\u9650\u516c\u53f8",
        operating_entity="Operator",
        approval_number=number,
        approval_date=approved_on,
        source_url="https://www.nppa.gov.cn/example.html",
        available_as_of=approved_on,
        retrieved_at=datetime(2026, 7, 12, tzinfo=timezone.utc),
    )


def test_century_huatong_high_attention_requires_multiple_supporting_factors(tmp_path):
    reference_date = date(2026, 7, 12)
    store = JsonArtifactStore(tmp_path)
    _seed_market_and_financials(
        store,
        "002602",
        reference_date=reference_date,
        rising=True,
        profit_yoy=50,
        cashflow=1_000,
    )
    JsonGameApprovalStore(tmp_path).save(
        [_approval(date(2026, 5, 25), "NPPA-1"), _approval(date(2026, 6, 29), "NPPA-2")]
    )

    snapshot = build_game_opportunity_snapshot(store, "002602", as_of_date=reference_date)

    assert snapshot.level is GameOpportunityLevel.HIGH_ATTENTION
    assert snapshot.score >= 8
    assert {item.factor_id for item in snapshot.factors} == {
        "approvals",
        "catalysts",
        "financial",
        "market",
    }
    assert next(item for item in snapshot.factors if item.factor_id == "approvals").score == 3


def test_negative_delivery_and_market_do_not_become_a_recommendation(tmp_path):
    reference_date = date(2026, 7, 12)
    store = JsonArtifactStore(tmp_path)
    _seed_market_and_financials(
        store,
        "002624",
        reference_date=reference_date,
        rising=False,
        profit_yoy=-66,
        cashflow=-1_000,
    )
    JsonGameApprovalStore(tmp_path).save([])

    snapshot = build_game_opportunity_snapshot(store, "002624", as_of_date=reference_date)

    assert snapshot.level is GameOpportunityLevel.LOW_SIGNAL
    assert snapshot.disclaimer.startswith("Attention score only")
    assert next(item for item in snapshot.factors if item.factor_id == "financial").score == 0
    assert next(item for item in snapshot.factors if item.factor_id == "market").score == 0


def test_missing_essential_data_is_explicit(tmp_path):
    store = JsonArtifactStore(tmp_path)

    snapshot = build_game_opportunity_snapshot(store, "002602", as_of_date=date(2026, 7, 12))

    assert snapshot.level is GameOpportunityLevel.INSUFFICIENT_DATA
    assert "Missing factor data" in snapshot.warnings[0]


def test_point_in_time_view_excludes_future_approval(tmp_path):
    reference_date = date(2026, 5, 31)
    store = JsonArtifactStore(tmp_path)
    _seed_market_and_financials(
        store,
        "002602",
        reference_date=reference_date,
        rising=True,
        profit_yoy=50,
        cashflow=1_000,
    )
    JsonGameApprovalStore(tmp_path).save(
        [_approval(date(2026, 5, 25), "NPPA-1"), _approval(date(2026, 6, 29), "NPPA-2")]
    )

    snapshot = build_game_opportunity_snapshot(store, "002602", as_of_date=reference_date)
    factor = next(item for item in snapshot.factors if item.factor_id == "approvals")

    assert factor.metrics["approvals_365d"] == 1
    assert factor.observed_as_of == date(2026, 5, 25)


def test_board_orders_covered_companies_by_attention_score(tmp_path):
    reference_date = date(2026, 7, 12)
    store = JsonArtifactStore(tmp_path)
    for symbol, rising, profit in [("002602", True, 50), ("002624", False, -20)]:
        _seed_market_and_financials(
            store,
            symbol,
            reference_date=reference_date,
            rising=rising,
            profit_yoy=profit,
            cashflow=1_000 if rising else -1_000,
        )
    JsonGameApprovalStore(tmp_path).save([_approval(date(2026, 6, 29), "NPPA-1")])

    board = build_game_opportunity_board(store, as_of_date=reference_date)

    assert [item.symbol for item in board] == ["002602", "002624"]


def test_unknown_symbol_has_no_game_opportunity_profile(tmp_path):
    snapshot = build_game_opportunity_snapshot(
        JsonArtifactStore(tmp_path), "600519", as_of_date=date(2026, 7, 12)
    )

    assert snapshot.available is False
    assert snapshot.level is GameOpportunityLevel.INSUFFICIENT_DATA
