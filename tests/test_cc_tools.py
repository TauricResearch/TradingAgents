"""Tests for cc_tools.py CLI bridge.

Each test runs cc_tools.py as a subprocess to verify it works correctly
when called from Claude Code subagents via Bash.
"""

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# Find the project root (where cc_tools.py lives)
PROJECT_ROOT = Path(__file__).parent.parent
CC_TOOLS = PROJECT_ROOT / "cc_tools.py"

# Find Python executable - prefer venv
PYTHON = str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe")
if not Path(PYTHON).exists():
    PYTHON = str(PROJECT_ROOT / ".venv" / "bin" / "python")
if not Path(PYTHON).exists():
    PYTHON = sys.executable


def run_cc_tools(*args, timeout=60):
    """Run cc_tools.py with given arguments and return (stdout, stderr, returncode)."""
    cmd = [PYTHON, str(CC_TOOLS)] + list(args)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(PROJECT_ROOT),
    )
    return result.stdout, result.stderr, result.returncode


class TestHelp:
    def test_help_output(self):
        stdout, stderr, rc = run_cc_tools("--help")
        assert rc == 0
        assert "get_stock_data" in stdout
        assert "memory_get" in stdout
        assert "save_results" in stdout

    def test_no_args_shows_help(self):
        stdout, stderr, rc = run_cc_tools()
        assert rc == 1  # should fail with no command


class TestStockData:
    def test_get_stock_data_returns_csv(self):
        stdout, stderr, rc = run_cc_tools(
            "get_stock_data", "AAPL", "2025-03-01", "2025-03-15"
        )
        assert rc == 0
        assert "AAPL" in stdout or "Date" in stdout or "Open" in stdout
        # Should contain CSV-like data
        lines = stdout.strip().split("\n")
        assert len(lines) > 2  # header + at least one data row

    def test_get_stock_data_invalid_ticker(self):
        stdout, stderr, rc = run_cc_tools(
            "get_stock_data", "INVALIDTICKER12345", "2025-03-01", "2025-03-15"
        )
        # Should either return empty/error but not crash
        assert rc == 0 or rc == 1


class TestIndicators:
    def test_get_rsi(self):
        stdout, stderr, rc = run_cc_tools(
            "get_indicators", "AAPL", "rsi", "2025-03-15"
        )
        assert rc == 0
        assert "rsi" in stdout.lower()

    def test_get_macd(self):
        stdout, stderr, rc = run_cc_tools(
            "get_indicators", "AAPL", "macd", "2025-03-15"
        )
        assert rc == 0
        assert "macd" in stdout.lower()

    def test_get_indicators_with_lookback(self):
        stdout, stderr, rc = run_cc_tools(
            "get_indicators", "AAPL", "rsi", "2025-03-15", "15"
        )
        assert rc == 0


class TestFundamentals:
    def test_get_fundamentals(self):
        stdout, stderr, rc = run_cc_tools(
            "get_fundamentals", "AAPL", "2025-03-15"
        )
        assert rc == 0
        assert len(stdout.strip()) > 50  # should have substantial content
        # Should contain some fundamental data keywords
        assert any(
            kw in stdout.lower()
            for kw in ["market cap", "pe ratio", "eps", "sector", "apple"]
        )

    def test_get_balance_sheet(self):
        stdout, stderr, rc = run_cc_tools(
            "get_balance_sheet", "AAPL"
        )
        assert rc == 0
        assert len(stdout.strip()) > 20

    def test_get_cashflow(self):
        stdout, stderr, rc = run_cc_tools(
            "get_cashflow", "AAPL"
        )
        assert rc == 0
        assert len(stdout.strip()) > 20

    def test_get_income_statement(self):
        stdout, stderr, rc = run_cc_tools(
            "get_income_statement", "AAPL"
        )
        assert rc == 0
        assert len(stdout.strip()) > 20


class TestNews:
    def test_get_news(self):
        # Use recent dates for better chance of finding news
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        stdout, stderr, rc = run_cc_tools(
            "get_news", "AAPL", start, end
        )
        assert rc == 0
        # May or may not find news, but should not crash

    def test_get_global_news(self):
        curr = datetime.now().strftime("%Y-%m-%d")
        stdout, stderr, rc = run_cc_tools(
            "get_global_news", curr
        )
        assert rc == 0

    def test_get_insider_transactions(self):
        stdout, stderr, rc = run_cc_tools(
            "get_insider_transactions", "AAPL"
        )
        assert rc == 0


class TestMemory:
    """Test memory persistence (add, get, clear)."""

    MEMORY_NAME = "pytest_test_memory"

    @pytest.fixture(autouse=True)
    def cleanup_memory(self):
        """Clean up test memory before and after each test."""
        run_cc_tools("memory_clear", self.MEMORY_NAME)
        yield
        run_cc_tools("memory_clear", self.MEMORY_NAME)

    def test_memory_add_and_get_roundtrip(self, tmp_path):
        # Write situation and advice to temp files
        sit_file = tmp_path / "situation.txt"
        adv_file = tmp_path / "advice.txt"
        sit_file.write_text("High inflation with rising interest rates affecting tech stocks")
        adv_file.write_text("Consider defensive sectors like utilities and consumer staples")

        # Add to memory
        stdout, stderr, rc = run_cc_tools(
            "memory_add", self.MEMORY_NAME,
            str(sit_file), str(adv_file)
        )
        assert rc == 0
        assert "Memory added" in stdout
        assert "Total entries: 1" in stdout

        # Query memory
        query_file = tmp_path / "query.txt"
        query_file.write_text("Rising rates impacting technology sector valuations")

        stdout, stderr, rc = run_cc_tools(
            "memory_get", self.MEMORY_NAME,
            str(query_file), "1"
        )
        assert rc == 0
        assert "defensive sectors" in stdout.lower() or "utilities" in stdout.lower()

    def test_memory_get_empty(self, tmp_path):
        query_file = tmp_path / "query.txt"
        query_file.write_text("Some query text")

        stdout, stderr, rc = run_cc_tools(
            "memory_get", self.MEMORY_NAME,
            str(query_file), "1"
        )
        assert rc == 0
        assert "No past memories found" in stdout

    def test_memory_multiple_entries(self, tmp_path):
        # Add two entries
        for i, (sit, adv) in enumerate([
            ("Bull market with tech sector leading gains", "Increase tech allocation"),
            ("Bear market with economic recession fears", "Reduce equity exposure"),
        ]):
            sit_file = tmp_path / f"sit_{i}.txt"
            adv_file = tmp_path / f"adv_{i}.txt"
            sit_file.write_text(sit)
            adv_file.write_text(adv)
            stdout, stderr, rc = run_cc_tools(
                "memory_add", self.MEMORY_NAME,
                str(sit_file), str(adv_file)
            )
            assert rc == 0

        # Query for something tech-related
        query_file = tmp_path / "query.txt"
        query_file.write_text("Tech stocks surging in bull market conditions")

        stdout, stderr, rc = run_cc_tools(
            "memory_get", self.MEMORY_NAME,
            str(query_file), "2"
        )
        assert rc == 0
        assert "Memory Match 1" in stdout
        assert "Memory Match 2" in stdout

    def test_memory_clear(self, tmp_path):
        # Add entry
        sit_file = tmp_path / "sit.txt"
        adv_file = tmp_path / "adv.txt"
        sit_file.write_text("test situation")
        adv_file.write_text("test advice")
        run_cc_tools("memory_add", self.MEMORY_NAME, str(sit_file), str(adv_file))

        # Clear
        stdout, stderr, rc = run_cc_tools("memory_clear", self.MEMORY_NAME)
        assert rc == 0
        assert "cleared" in stdout.lower()

        # Verify empty
        query_file = tmp_path / "query.txt"
        query_file.write_text("test")
        stdout, stderr, rc = run_cc_tools(
            "memory_get", self.MEMORY_NAME, str(query_file)
        )
        assert "No past memories found" in stdout


class TestSaveResults:
    def test_save_results(self, tmp_path):
        state = {
            "company_of_interest": "TEST",
            "trade_date": "2025-03-15",
            "market_report": "Test market report",
            "sentiment_report": "Test sentiment report",
            "news_report": "Test news report",
            "fundamentals_report": "Test fundamentals report",
            "investment_debate_state": {
                "bull_history": "Bull argument",
                "bear_history": "Bear argument",
                "history": "Full debate",
                "current_response": "Latest",
                "judge_decision": "Buy",
            },
            "trader_investment_plan": "Buy ASAP",
            "risk_debate_state": {
                "aggressive_history": "Go big",
                "conservative_history": "Be cautious",
                "neutral_history": "Balance",
                "history": "Full risk debate",
                "judge_decision": "Buy with limits",
            },
            "investment_plan": "Investment plan text",
            "final_trade_decision": "Buy",
        }

        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps(state))

        stdout, stderr, rc = run_cc_tools(
            "save_results", "TEST", "2025-03-15", str(state_file)
        )
        assert rc == 0
        assert "Results saved" in stdout

        # Verify the output file exists
        out_path = PROJECT_ROOT / "eval_results" / "TEST" / "TradingAgentsStrategy_logs" / "full_states_log_2025-03-15.json"
        assert out_path.exists()

        # Verify content
        with open(out_path) as f:
            saved = json.load(f)
        assert "2025-03-15" in saved
        assert saved["2025-03-15"]["market_report"] == "Test market report"
        assert saved["2025-03-15"]["final_trade_decision"] == "Buy"

        # Clean up
        out_path.unlink()
        out_path.parent.rmdir()
        (PROJECT_ROOT / "eval_results" / "TEST").rmdir()
