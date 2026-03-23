"""Integration tests for the Claude Code TradingAgents pipeline.

These tests verify that the full data pipeline works end-to-end,
including data fetching, memory persistence, and results saving.

This does NOT test the actual Claude Code subagent orchestration
(which requires a running Claude Code session), but verifies all
the infrastructure that subagents depend on.
"""

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
CC_TOOLS = PROJECT_ROOT / "cc_tools.py"

PYTHON = str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe")
if not Path(PYTHON).exists():
    PYTHON = str(PROJECT_ROOT / ".venv" / "bin" / "python")
if not Path(PYTHON).exists():
    PYTHON = sys.executable


def run(*args, timeout=60):
    result = subprocess.run(
        [PYTHON, str(CC_TOOLS)] + list(args),
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(PROJECT_ROOT),
    )
    return result.stdout, result.stderr, result.returncode


class TestFullAnalystDataPipeline:
    """Simulate what the 4 analyst subagents would do: fetch all data for a ticker."""

    TICKER = "MSFT"
    TRADE_DATE = "2025-03-15"
    START_30D = "2025-02-13"
    START_7D = "2025-03-08"

    def test_market_analyst_data(self):
        """Market analyst fetches stock data + indicators."""
        # Stock data
        stdout, _, rc = run("get_stock_data", self.TICKER, self.START_30D, self.TRADE_DATE)
        assert rc == 0
        assert "Open" in stdout or "Close" in stdout
        stock_lines = [l for l in stdout.strip().split("\n") if not l.startswith("#")]
        assert len(stock_lines) >= 2  # header + data

        # Indicators
        for indicator in ["rsi", "macd", "close_50_sma"]:
            stdout, _, rc = run("get_indicators", self.TICKER, indicator, self.TRADE_DATE)
            assert rc == 0
            assert len(stdout.strip()) > 10

    def test_social_analyst_data(self):
        """Social media analyst fetches company news."""
        stdout, _, rc = run("get_news", self.TICKER, self.START_7D, self.TRADE_DATE)
        assert rc == 0  # may have no news but should not crash

    def test_news_analyst_data(self):
        """News analyst fetches company + global news."""
        stdout, _, rc = run("get_news", self.TICKER, self.START_7D, self.TRADE_DATE)
        assert rc == 0

        stdout, _, rc = run("get_global_news", self.TRADE_DATE, "7", "5")
        assert rc == 0

    def test_fundamentals_analyst_data(self):
        """Fundamentals analyst fetches all financial statements."""
        stdout, _, rc = run("get_fundamentals", self.TICKER, self.TRADE_DATE)
        assert rc == 0
        assert len(stdout.strip()) > 50

        stdout, _, rc = run("get_balance_sheet", self.TICKER, "quarterly", self.TRADE_DATE)
        assert rc == 0

        stdout, _, rc = run("get_cashflow", self.TICKER, "quarterly", self.TRADE_DATE)
        assert rc == 0

        stdout, _, rc = run("get_income_statement", self.TICKER, "quarterly", self.TRADE_DATE)
        assert rc == 0


class TestMemoryPersistenceAcrossInvocations:
    """Verify memory works across separate CLI invocations (simulating separate subagents)."""

    MEMORY_NAME = "integration_test_memory"

    @pytest.fixture(autouse=True)
    def cleanup(self):
        run("memory_clear", self.MEMORY_NAME)
        yield
        run("memory_clear", self.MEMORY_NAME)

    def test_memory_persists_across_calls(self, tmp_path):
        """Add memory in one call, retrieve in another — simulates cross-agent persistence."""
        # First invocation: add a memory
        sit = tmp_path / "sit.txt"
        adv = tmp_path / "adv.txt"
        sit.write_text(
            "AAPL showing strong growth in services revenue with expanding margins. "
            "iPhone sales declining but offset by services and wearables growth."
        )
        adv.write_text(
            "The bull case was correct. Services growth proved more durable than expected. "
            "Lesson: Don't underweight services revenue growth trajectory."
        )
        stdout, _, rc = run("memory_add", self.MEMORY_NAME, str(sit), str(adv))
        assert rc == 0

        # Second invocation: add another memory
        sit2 = tmp_path / "sit2.txt"
        adv2 = tmp_path / "adv2.txt"
        sit2.write_text(
            "NVDA GPU demand surging due to AI infrastructure buildout. "
            "Data center revenue growing 200% year over year."
        )
        adv2.write_text(
            "The aggressive stance was justified. AI infrastructure spend continued. "
            "Lesson: When there's a genuine paradigm shift, be more aggressive."
        )
        stdout, _, rc = run("memory_add", self.MEMORY_NAME, str(sit2), str(adv2))
        assert rc == 0
        assert "Total entries: 2" in stdout

        # Third invocation: query for similar situations
        query = tmp_path / "query.txt"
        query.write_text(
            "Apple services segment showing accelerating growth while hardware sales plateau."
        )
        stdout, _, rc = run("memory_get", self.MEMORY_NAME, str(query), "2")
        assert rc == 0
        assert "Memory Match 1" in stdout
        assert "Memory Match 2" in stdout


class TestEndToEndResultsSaving:
    """Test the full results save/load cycle."""

    def test_save_and_verify_structure(self, tmp_path):
        """Verify saved results match the original TradingAgentsGraph._log_state format."""
        state = {
            "company_of_interest": "INTEGRATION_TEST",
            "trade_date": "2025-03-15",
            "market_report": "Market is trending upward with strong momentum indicators.",
            "sentiment_report": "Social media sentiment is overwhelmingly positive.",
            "news_report": "Recent earnings beat expectations. Fed holds rates steady.",
            "fundamentals_report": "Strong balance sheet with growing free cash flow.",
            "investment_debate_state": {
                "bull_history": "Bull Analyst: Strong growth trajectory...",
                "bear_history": "Bear Analyst: Overvalued at current levels...",
                "history": "Bull Analyst: Strong growth...\nBear Analyst: Overvalued...",
                "current_response": "Bear Analyst: Overvalued at current levels...",
                "judge_decision": "Buy - bull case is more compelling",
            },
            "investment_plan": "Buy with a 12-month horizon, position size 5% of portfolio.",
            "trader_investment_plan": "FINAL TRANSACTION PROPOSAL: **BUY**",
            "risk_debate_state": {
                "aggressive_history": "Aggressive: Go all in...",
                "conservative_history": "Conservative: Limit to 3%...",
                "neutral_history": "Neutral: 5% seems right...",
                "history": "Aggressive: Go all in...\nConservative: Limit...\nNeutral: 5%...",
                "judge_decision": "Buy with 5% position size, stop loss at -10%",
            },
            "final_trade_decision": "**Buy** - Position size: 5% of portfolio. Stop loss: -10%.",
        }

        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps(state))

        stdout, _, rc = run("save_results", "INTEGRATION_TEST", "2025-03-15", str(state_file))
        assert rc == 0
        assert "Results saved" in stdout

        # Verify file structure matches original format
        out_path = (
            PROJECT_ROOT
            / "eval_results"
            / "INTEGRATION_TEST"
            / "TradingAgentsStrategy_logs"
            / "full_states_log_2025-03-15.json"
        )
        assert out_path.exists()

        with open(out_path) as f:
            saved = json.load(f)

        entry = saved["2025-03-15"]

        # Verify all expected fields exist (matching TradingAgentsGraph._log_state)
        assert entry["company_of_interest"] == "INTEGRATION_TEST"
        assert entry["trade_date"] == "2025-03-15"
        assert "market_report" in entry
        assert "sentiment_report" in entry
        assert "news_report" in entry
        assert "fundamentals_report" in entry
        assert "investment_debate_state" in entry
        assert "investment_plan" in entry
        assert "final_trade_decision" in entry
        assert "risk_debate_state" in entry
        assert "trader_investment_decision" in entry

        # Verify nested structure
        assert "bull_history" in entry["investment_debate_state"]
        assert "bear_history" in entry["investment_debate_state"]
        assert "judge_decision" in entry["investment_debate_state"]
        assert "aggressive_history" in entry["risk_debate_state"]
        assert "conservative_history" in entry["risk_debate_state"]
        assert "neutral_history" in entry["risk_debate_state"]

        # Clean up
        out_path.unlink()
        out_path.parent.rmdir()
        (PROJECT_ROOT / "eval_results" / "INTEGRATION_TEST").rmdir()
