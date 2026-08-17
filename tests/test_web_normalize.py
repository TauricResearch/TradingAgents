from backend.integrations.india import normalize_india_symbol, search_catalog
from backend.integrations.normalize import map_action, normalize_final_state, plain_language


def test_india_symbol_defaults_to_nse():
    symbol, exchange = normalize_india_symbol("reliance")
    assert symbol == "RELIANCE.NS"
    assert exchange == "NSE"


def test_search_catalog_finds_hdfc():
    rows = search_catalog("HDFC")
    assert any(row["symbol"] == "HDFCBANK.NS" for row in rows)


def test_normalize_does_not_invent_prices():
    state = {
        "final_trade_decision": "**Rating**: Buy\n\n**Executive Summary**: Strong cash flows.\n\n**Investment Thesis**: Balance sheet is healthy.",
        "trader_investment_plan": "**Action**: Buy\n\n**Reasoning**: Momentum is constructive.",
        "investment_debate_state": {"bull_history": "Growth runway.", "bear_history": "Valuation risk.", "judge_decision": "Lean long."},
        "risk_debate_state": {"judge_decision": "**Rating**: Buy\n\n**Executive Summary**: Size modestly."},
        "market_report": "RSI is not overbought.",
    }
    result = normalize_final_state("RELIANCE.NS", state, "Buy")
    assert result["action"] == "BUY"
    assert result["entry_price"] is None
    assert result["price_target"] is None
    assert "Reliance" in result["in_plain_language"] or "RELIANCE" in result["in_plain_language"].upper()


def test_map_action_overweight():
    assert map_action("Overweight") == "BUY"
    assert map_action("Underweight") == "SELL"


def test_plain_language_hold():
    text = plain_language("HOLD", "Hold", "Evidence is mixed.", "INFY.NS")
    assert "wait" in text.lower() or "Hold" in text
