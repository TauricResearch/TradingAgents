from datetime import date, datetime, timedelta, timezone

from tradingagents.research_platform.agent_contracts import (
    AnalystNote,
    ConfidenceLevel,
    EvidenceRef,
    InvestmentThesis,
    TradeDirection,
    TradeHorizon,
    TradeSignal,
)
from tradingagents.research_platform.backtest_contracts import (
    BacktestConfig,
    BacktestMetrics,
    BacktestResult,
    BacktestTrade,
    EquityPoint,
)
from tradingagents.research_platform.data_contracts import (
    DataProvenance,
    FundamentalSnapshot,
    NewsItem,
    PriceBar,
)
from tradingagents.research_platform.research_report import (
    ResearchReportBundle,
    render_research_report,
    write_research_report,
)
from tradingagents.research_platform.risk_contracts import (
    RiskDecision,
    RiskLimitBreach,
    RiskReview,
)


def _provenance(day: date) -> DataProvenance:
    return DataProvenance(
        provider="fixture",
        as_of_date=day,
        retrieved_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
        source="fixture",
        vendor_symbol="NVDA",
    )


def _evidence() -> EvidenceRef:
    return EvidenceRef(
        source_id="price:NVDA:2026-01-05",
        description="Price snapshot",
        as_of_date=date(2026, 1, 5),
        confidence=0.95,
    )


def _bundle() -> ResearchReportBundle:
    signal = TradeSignal(
        symbol="NVDA",
        as_of_date=date(2026, 1, 5),
        direction=TradeDirection.BUY,
        horizon=TradeHorizon.MEDIUM,
        confidence=0.75,
        rationale="Risk/reward is favorable.",
        proposed_position_pct=0.05,
        evidence=[_evidence()],
    )
    return ResearchReportBundle(
        symbol="NVDA",
        as_of_date=datetime(2026, 1, 5, tzinfo=timezone.utc),
        generated_at=datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc),
        price_bars=[
            PriceBar(
                symbol="NVDA",
                date=date(2026, 1, 2),
                open=100,
                high=105,
                low=99,
                close=104,
                adjusted_close=103.5,
                volume=1000,
                currency="USD",
                provenance=_provenance(date(2026, 1, 2)),
            ),
            PriceBar(
                symbol="NVDA",
                date=date(2026, 1, 5),
                open=105,
                high=110,
                low=104,
                close=108,
                adjusted_close=108,
                volume=2000,
                currency="USD",
                provenance=_provenance(date(2026, 1, 5)),
            ),
        ],
        fundamentals=[
            FundamentalSnapshot(
                symbol="NVDA",
                period_end=date(2026, 1, 5),
                fiscal_period="snapshot",
                currency="USD",
                metrics={"market_cap": 3000000000000, "pe_ratio_ttm": 42.5},
                provenance=_provenance(date(2026, 1, 5)),
            )
        ],
        news=[
            NewsItem(
                symbol="NVDA",
                title="Nvidia launches platform",
                published_at=datetime(2026, 1, 4, 15, 30, tzinfo=timezone.utc),
                as_of_date=date(2026, 1, 5),
                provider="Example News",
                url="https://example.com/nvda",
                summary="Summary.",
                source_id="news-1",
            )
        ],
        analyst_notes=[
            AnalystNote(
                symbol="NVDA",
                analyst_role="Market Analyst",
                as_of_date=date(2026, 1, 5),
                summary="Trend is constructive.",
                evidence=[_evidence()],
                confidence=ConfidenceLevel.HIGH,
            )
        ],
        thesis=InvestmentThesis(
            symbol="NVDA",
            as_of_date=date(2026, 1, 5),
            base_case="Base case.",
            bull_case="Bull case.",
            bear_case="Bear case.",
            confidence=0.7,
        ),
        signal=signal,
        risk_review=RiskReview(
            symbol="NVDA",
            as_of_date=date(2026, 1, 5),
            decision=RiskDecision.REDUCE,
            approved_position_pct=0.03,
            breaches=[
                RiskLimitBreach(
                    rule="max_single_position_pct",
                    observed=0.05,
                    limit=0.03,
                    message="Position capped.",
                )
            ],
            notes=["Position capped at policy maximum."],
        ),
        backtest_result=BacktestResult(
            config=BacktestConfig(
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 5),
                initial_cash=1000,
                symbols=["NVDA"],
            ),
            metrics=BacktestMetrics(
                total_return_pct=0.08,
                cagr_pct=0.12,
                annualized_volatility_pct=0.2,
                sharpe=1.1,
                sortino=None,
                max_drawdown_pct=0.05,
                turnover_pct=0.5,
                average_exposure_pct=0.4,
            ),
            trades=[
                BacktestTrade(
                    symbol="NVDA",
                    date=date(2026, 1, 3),
                    direction=TradeDirection.BUY,
                    quantity=5,
                    price=100,
                    notional=500,
                    commission=1,
                    source_signal_date=date(2026, 1, 2),
                )
            ],
            equity_curve=[
                EquityPoint(
                    date=date(2026, 1, 5),
                    equity=1080,
                    cash=500,
                    gross_exposure_pct=0.5,
                    net_exposure_pct=0.5,
                )
            ],
        ),
    )


def test_render_research_report_contains_all_major_sections():
    report = render_research_report(_bundle())

    assert "# Personal Research Report: NVDA" in report
    assert "## Market Snapshot" in report
    assert "USD 108.00" in report
    assert "## Fundamentals" in report
    assert "market_cap" in report
    assert "## News" in report
    assert "[Nvidia launches platform](https://example.com/nvda)" in report
    assert "## Analyst Notes" in report
    assert "## Investment Thesis" in report
    assert "## Trade Signal" in report
    assert "**Direction:** buy" in report
    assert "## Risk Review" in report
    assert "**Decision:** reduce" in report
    assert "## Backtest" in report
    assert "| Total Return | 8.00% |" in report
    assert "## Provenance" in report


def test_render_research_report_handles_empty_optional_artifacts():
    bundle = ResearchReportBundle(
        symbol="NVDA",
        as_of_date=datetime(2026, 1, 5, tzinfo=timezone.utc),
    )

    report = render_research_report(bundle)

    assert "No normalized price bars available." in report
    assert "No validated trade signal available." in report
    assert "No deterministic risk review available." in report
    assert "No backtest result available." in report


def test_write_research_report_creates_markdown_file(tmp_path):
    path = write_research_report(_bundle(), tmp_path)

    assert path.name == "NVDA_2026-01-05.md"
    assert path.exists()
    assert "# Personal Research Report: NVDA" in path.read_text(encoding="utf-8")


def test_render_research_report_renders_financial_quality_separately():
    bundle = ResearchReportBundle(
        symbol="600519",
        as_of_date=datetime(2026, 4, 1, tzinfo=timezone.utc),
        fundamentals=[
            FundamentalSnapshot(
                symbol="600519",
                period_end=date(2025, 12, 31),
                fiscal_period="financial_report_2025-12-31",
                currency="CNY",
                metrics={"return_on_equity_pct": 15.0, "reported_net_income": 100.0},
                provenance=_provenance(date(2026, 4, 1)),
            )
        ],
    )

    report = render_research_report(bundle)

    assert "## Financial Quality" in report
    assert "**Report Period:** 2025-12-31" in report
    assert "return_on_equity_pct" in report
    assert "## Financial Health" in report
    assert "**Status:** watch" in report


def test_render_research_report_renders_financial_trend_for_multiple_periods():
    fundamentals = [
        FundamentalSnapshot(
            symbol="600519",
            period_end=date(2025, 12, 31),
            fiscal_period="financial_report_2025-12-31",
            metrics={"reported_total_revenue": 1000.0, "return_on_equity_pct": 15.0},
            provenance=_provenance(date(2026, 3, 1)),
        ),
        FundamentalSnapshot(
            symbol="600519",
            period_end=date(2025, 9, 30),
            fiscal_period="financial_report_2025-09-30",
            metrics={"reported_total_revenue": 900.0, "return_on_equity_pct": 14.0},
            provenance=_provenance(date(2025, 10, 30)),
        ),
    ]

    report = render_research_report(
        ResearchReportBundle(
            symbol="600519",
            as_of_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            fundamentals=fundamentals,
        )
    )

    assert "## Financial Trend" in report
    assert "| 2025-12-31 |" in report
    assert "| Report Period | Revenue | Net Income | Operating Cash Flow | ROE (%) |" in report


def test_render_research_report_renders_historical_valuation_context():
    fundamentals = [
        FundamentalSnapshot(
            symbol="600519",
            period_end=date(2026, 1, 1) + timedelta(days=index),
            fiscal_period="daily_snapshot",
            metrics={
                "pe_ratio_ttm": float(index + 10),
                "price_to_book": 3.0,
                "price_to_sales_ttm": 2.0,
                "dividend_yield_pct": 2.0,
            },
            provenance=_provenance(date(2026, 2, 1)),
        )
        for index in range(20)
    ]

    report = render_research_report(
        ResearchReportBundle(
            symbol="600519",
            as_of_date=datetime(2026, 2, 1, tzinfo=timezone.utc),
            fundamentals=fundamentals,
        )
    )

    assert "## Research Readiness" in report
    assert "**Status:** incomplete" in report
    assert "## Valuation Context" in report
    assert "**Daily Snapshot As Of:** 2026-01-20" in report
    assert "| P/E (TTM) | 29 | 100 | 10 | 19.5 | 29 | 20 |" in report


def test_render_research_report_renders_vendor_company_profile():
    report = render_research_report(
        ResearchReportBundle(
            symbol="600519",
            as_of_date=datetime(2026, 7, 10, tzinfo=timezone.utc),
            fundamentals=[
                FundamentalSnapshot(
                    symbol="600519",
                    period_end=date(2026, 7, 10),
                    fiscal_period="daily_snapshot",
                    metrics={
                        "company_name": "Kweichow Moutai",
                        "company_industry": "Liquor",
                        "company_list_date": "20010827",
                    },
                    provenance=_provenance(date(2026, 7, 10)),
                )
            ],
        )
    )

    assert "## Company Profile" in report
    assert "| Name | Kweichow Moutai |" in report
    assert "| Listing Date | 2001-08-27 |" in report
