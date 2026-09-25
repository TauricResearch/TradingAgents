from tradingagents.agents.utils.crypto_memory import CryptoTrainingMemory


def test_crypto_memory_writes_raw_and_lessons_only(tmp_path):
    memory = CryptoTrainingMemory({"crypto_memory_dir": str(tmp_path)})
    memory.store_run(
        "BTC/USDT",
        "2026-05-10",
        {
            "final_trade_decision": "Rating: Hold\nWait for breakout.",
            "market_report": "range-bound",
            "news_report": "no major catalyst",
            "sentiment_report": "neutral",
            "fundamentals_report": "",
            "investment_plan": "wait",
            "trader_investment_plan": "hold",
        },
    )
    memory.add_lesson(
        "BTC/USDT",
        "2026-05-10",
        "Range chop after high funding should be treated as no-trade unless volume confirms breakout.",
        {"pnl_pct": 0.0},
    )

    assert (tmp_path / "raw.jsonl").exists()
    assert (tmp_path / "lessons.jsonl").exists()
    assert len(memory.load_entries()) == 1

    context = memory.get_past_context("BTC/USDT")
    assert "Reviewed lessons for BTC/USDT" in context
    assert "Range chop" in context
    assert memory.get_pending_entries() == []
