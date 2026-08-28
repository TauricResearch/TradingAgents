# Modified for A-share position management; see repository NOTICE.
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from cli.utils import detect_asset_type
from tradingagents.a_share import (
    build_a_share_analysis_context,
    is_a_share_symbol,
    normalize_portfolio_context,
    render_a_share_context,
)
from tradingagents.agents.analysts.sentiment_analyst import create_sentiment_analyst
from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.managers.research_manager import create_research_manager
from tradingagents.agents.schemas import (
    PositionAction,
    PositionManagementDecision,
    PositionManagementPlan,
    PositionManagementProposal,
    SentimentBand,
    SentimentReport,
    render_position_management_decision,
)
from tradingagents.agents.trader.trader import create_trader
from tradingagents.agents.utils.rating import parse_position_action
from tradingagents.dataflows.symbol_utils import normalize_symbol
from tradingagents.graph.signal_processing import SignalProcessor


@pytest.mark.unit
def test_bare_a_share_symbols_are_normalized_and_detected():
    assert normalize_symbol("600968") == "600968.SS"
    assert normalize_symbol("000001") == "000001.SZ"
    assert normalize_symbol("300750") == "300750.SZ"
    assert normalize_symbol("688981.SH") == "688981.SS"
    assert is_a_share_symbol("830799.BJ")
    assert detect_asset_type("600968").value == "a_share"


@pytest.mark.unit
def test_portfolio_context_validation():
    context = normalize_portfolio_context(
        {"cost_basis": "3.65", "position_pct": "8", "shares": 1000}
    )
    assert context["cost_basis"] == 3.65
    assert context["position_pct"] == 8.0
    assert context["shares"] == 1000
    with pytest.raises(ValueError):
        normalize_portfolio_context({"position_pct": 101})


def _bars() -> pd.DataFrame:
    closes = [8 + i * 0.05 for i in range(80)]
    return pd.DataFrame(
        {
            "date": pd.date_range(end=date.today(), periods=80),
            "open": closes,
            "close": closes,
            "high": [x + 0.1 for x in closes],
            "low": [x - 0.1 for x in closes],
            "volume_lots": [1000] * 80,
            "amount": [1_000_000] * 80,
            "amplitude_pct": [2.0] * 80,
            "return_pct": [0.5] * 80,
            "change": [0.05] * 80,
            "turnover_pct": [1.2] * 80,
        }
    )


@pytest.mark.unit
def test_three_dimensional_matrix_uses_valuation_trend_and_position():
    with (
        patch(
            "tradingagents.a_share.context._fetch_bars",
            return_value=("示例公司", _bars()),
        ),
        patch(
            "tradingagents.a_share.context._fetch_quote",
            return_value={"name": "示例公司", "pe_ttm": 10.0, "pb": 1.0},
        ),
        patch(
            "tradingagents.a_share.context._benchmark_environment",
            return_value={"CSI 300": {"close": 4000, "20d_return_pct": 2.0}},
        ),
    ):
        low = build_a_share_analysis_context(
            "600968",
            date.today().isoformat(),
            {"position_pct": 2},
        )
        high = build_a_share_analysis_context(
            "600968",
            date.today().isoformat(),
            {"position_pct": 20},
        )
    assert low["dimensions"] == {
        "valuation": "cheap",
        "trend": "neutral",
        "position": "low",
    }
    assert low["matrix_action"] == "Slight Add"
    assert high["matrix_action"] == "Hold"
    assert "T+1" in render_a_share_context(low)


@pytest.mark.unit
def test_a_share_decision_render_and_signal_parser():
    decision = PositionManagementDecision(
        action=PositionAction.REDUCE,
        target_position_pct=8,
        executive_summary="Trim concentration.",
        investment_thesis="Valuation is fair but trend is weak.",
        matrix_baseline=PositionAction.REDUCE,
        execution_plan="Sell in two tranches.",
        risk_constraints="Do not sell shares bought today.",
        review_trigger="Review after the next earnings report.",
    )
    rendered = render_position_management_decision(decision)
    assert "**Position Action**: Reduce" in rendered
    assert parse_position_action(rendered) == "Reduce"
    assert SignalProcessor().process_signal(rendered) == "Reduce"


@pytest.mark.unit
def test_a_share_order_and_matrix_constraints_are_hard_validated():
    with pytest.raises(ValueError, match="multiples of 100"):
        PositionManagementProposal(
            action=PositionAction.ADD,
            reasoning="x",
            target_position_pct=5,
            stop_or_invalidation="x",
            order_shares=150,
        )
    with pytest.raises(ValueError, match="matrix_deviation_reason"):
        PositionManagementDecision(
            action=PositionAction.ADD,
            target_position_pct=10,
            executive_summary="x",
            investment_thesis="x",
            matrix_baseline=PositionAction.HOLD,
            execution_plan="x",
            risk_constraints="x",
            review_trigger="x",
        )


@pytest.mark.unit
def test_a_share_sentiment_does_not_fetch_us_community_sources():
    report = SentimentReport(
        overall_band=SentimentBand.NEUTRAL,
        overall_score=5,
        confidence="medium",
        narrative="China market context only.",
    )
    structured = MagicMock()
    structured.invoke.return_value = report
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    llm.invoke.return_value = MagicMock(content="fallback")
    state = {
        "company_of_interest": "600968.SS",
        "trade_date": "2026-07-23",
        "asset_type": "a_share",
        "instrument_context": "A-share",
        "a_share_context": {
            "mode": "a_share",
            "symbol": "600968.SH",
            "name": "海油发展",
            "trade_date": "2026-07-23",
            "source": "test",
            "market": {
                "close": 3.88,
                "ma20": 3.58,
                "ma60": 3.88,
                "rsi14": 61,
                "turnover_pct": 0.47,
                "pe_ttm": 15.47,
                "pb": 1.38,
            },
            "portfolio": normalize_portfolio_context({"position_pct": 8}),
            "dimensions": {"valuation": "fair", "trend": "neutral", "position": "medium"},
            "matrix_action": "Hold",
            "matrix_action_zh": "不动",
            "trading_rules": {"settlement": "T+1"},
            "china_market_environment": {"CSI 300": {"20d_return_pct": -2}},
        },
        "messages": [],
    }
    with (
        patch(
            "tradingagents.agents.analysts.sentiment_analyst.fetch_stocktwits_messages"
        ) as stocktwits,
        patch(
            "tradingagents.agents.analysts.sentiment_analyst.fetch_reddit_posts"
        ) as reddit,
    ):
        create_sentiment_analyst(llm)(state)
    stocktwits.assert_not_called()
    reddit.assert_not_called()


def _a_share_state() -> dict:
    state = {
        "company_of_interest": "600968.SS",
        "trade_date": "2026-07-23",
        "asset_type": "a_share",
        "instrument_context": "A-share instrument",
        "a_share_context": {
            "mode": "a_share",
            "symbol": "600968.SH",
            "name": "海油发展",
            "trade_date": "2026-07-23",
            "source": "test",
            "market": {
                "close": 3.88,
                "ma20": 3.58,
                "ma60": 3.88,
                "rsi14": 61,
                "turnover_pct": 0.47,
                "pe_ttm": 15.47,
                "pb": 1.38,
            },
            "portfolio": normalize_portfolio_context(
                {"cost_basis": 3.65, "position_pct": 8, "shares": 10000}
            ),
            "dimensions": {"valuation": "fair", "trend": "neutral", "position": "medium"},
            "matrix_action": "Hold",
            "matrix_action_zh": "不动",
            "trading_rules": {"settlement": "T+1", "buy_lot_size": 100},
            "china_market_environment": {"CSI 300": {"20d_return_pct": -2}},
        },
        "investment_debate_state": {
            "history": "Balanced debate.",
            "bull_history": "",
            "bear_history": "",
            "current_response": "",
            "judge_decision": "",
            "count": 1,
        },
        "investment_plan": "placeholder",
        "trader_investment_plan": "placeholder",
        "risk_debate_state": {
            "history": "Risk debate.",
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "latest_speaker": "",
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
            "judge_decision": "",
            "count": 1,
        },
        "past_context": "",
    }
    return state


def _schema_llm(results: dict[type, object]) -> MagicMock:
    llm = MagicMock()

    def bind(schema):
        structured = MagicMock()
        structured.invoke.return_value = results.get(schema)
        return structured

    llm.with_structured_output.side_effect = bind
    return llm


@pytest.mark.unit
def test_a_share_manager_trader_and_pm_use_position_management_schemas():
    state = _a_share_state()

    research = PositionManagementPlan(
        action=PositionAction.HOLD,
        rationale="Matrix and evidence agree.",
        target_position_pct=8,
        execution_plan="No trade.",
    )
    rm = create_research_manager(_schema_llm({PositionManagementPlan: research}))
    state.update(rm(state))
    assert "**Position Action**: Hold" in state["investment_plan"]
    assert "Buy" not in state["investment_plan"]

    proposal = PositionManagementProposal(
        action=PositionAction.HOLD,
        reasoning="No favorable adjustment edge.",
        target_position_pct=8,
        stop_or_invalidation="Review below support.",
        order_shares=0,
    )
    trader = create_trader(_schema_llm({PositionManagementProposal: proposal}))
    state.update(trader(state))
    assert "FINAL POSITION ACTION: **HOLD**" in state["trader_investment_plan"]

    decision = PositionManagementDecision(
        action=PositionAction.HOLD,
        target_position_pct=8,
        executive_summary="Maintain the position.",
        investment_thesis="Valuation is fair and trend is neutral.",
        matrix_baseline=PositionAction.HOLD,
        execution_plan="No order.",
        risk_constraints="Respect T+1 and concentration limits.",
        review_trigger="Review on a matrix-dimension change.",
    )
    pm = create_portfolio_manager(_schema_llm({PositionManagementDecision: decision}))
    result = pm(state)
    assert "**Position Action**: Hold" in result["final_trade_decision"]
    assert "**Matrix Baseline**: Hold" in result["final_trade_decision"]
