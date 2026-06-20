"""Tests for the portfolio holdings system.

Covers:
1. Sync from Google Sheet (requires gws auth)
2. Local JSON repository read/write
3. Data validation and normalization
4. Prompt generation for each agent type
5. Backward compatibility with legacy holdings dict
"""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tradingagents.portfolio import (
    Holding,
    Portfolio,
    PortfolioMetadata,
    PortfolioRepository,
    build_pm_prompt,
    build_risk_prompt,
    build_trader_prompt,
    normalize_ticker,
    validate_holding,
)

class _TempDirMixin:
    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(str(self._tmp), ignore_errors=True)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class TestHolding:
    def test_to_dict_excludes_none(self):
        h = Holding(ticker="002241.SZ", shares=100, avg_cost=10.0)
        d = h.to_dict()
        assert d == {"ticker": "002241.SZ", "shares": 100, "avg_cost": 10.0}
        assert "market_price" not in d

    def test_from_dict_roundtrip(self):
        h = Holding(
            ticker="002241.SZ",
            name="歌尔股份",
            shares=4500,
            avg_cost=28.41,
            market_price=25.37,
            pnl_pct=-0.107,
        )
        d = h.to_dict()
        h2 = Holding.from_dict(d)
        assert h2.ticker == h.ticker
        assert h2.shares == h.shares
        assert h2.pnl_pct == h.pnl_pct


class TestPortfolio:
    def test_total_invested(self):
        p = Portfolio(
            holdings={
                "A": Holding(ticker="A", shares=100, avg_cost=10.0),
                "B": Holding(ticker="B", shares=200, avg_cost=5.0),
            }
        )
        assert p.total_invested() == 2000.0

    def test_to_dict_roundtrip(self):
        p = Portfolio(
            holdings={
                "002241.SZ": Holding(ticker="002241.SZ", shares=100, avg_cost=10.0),
            },
            metadata=PortfolioMetadata(updated_at="2026-01-01T00:00:00+00:00"),
            summary={"total_holdings": 1},
        )
        d = p.to_dict()
        p2 = Portfolio.from_dict(d)
        assert len(p2.holdings) == 1
        assert p2.summary["total_holdings"] == 1


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

class TestNormalizeTicker:
    def test_a_share_6_prefix(self):
        assert normalize_ticker("600519") == "600519.SS"

    def test_a_share_0_prefix(self):
        assert normalize_ticker("002241") == "002241.SZ"

    def test_a_share_3_prefix(self):
        assert normalize_ticker("300002") == "300002.SZ"

    def test_hk_unchanged(self):
        assert normalize_ticker("HK1810") == "HK1810"

    def test_skip_headers(self):
        assert normalize_ticker("合计") is None
        assert normalize_ticker("可用现金") is None
        assert normalize_ticker("-") is None


class TestValidateHolding:
    def test_valid_holding(self):
        h = Holding(ticker="A", shares=100, avg_cost=10.0)
        assert validate_holding(h) is h

    def test_invalid_shares(self):
        h = Holding(ticker="A", shares=0, avg_cost=10.0)
        assert validate_holding(h) is None

    def test_invalid_cost(self):
        h = Holding(ticker="A", shares=100, avg_cost=-1.0)
        assert validate_holding(h) is None


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class TestPortfolioRepository:
    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = PortfolioRepository(data_path=os.path.join(tmpdir, "portfolio.json"))
            p = Portfolio(
                holdings={
                    "002241.SZ": Holding(ticker="002241.SZ", shares=100, avg_cost=10.0),
                },
                metadata=PortfolioMetadata(updated_at="2026-01-01T00:00:00+00:00"),
            )
            repo.save(p)
            assert repo.exists()

            p2 = repo.load()
            assert p2.holdings["002241.SZ"].shares == 100

    def test_load_missing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = PortfolioRepository(data_path=os.path.join(tmpdir, "missing.json"))
            with pytest.raises(FileNotFoundError):
                repo.load()

    def test_corrupted_json_backup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "portfolio.json"
            path.write_text("not json", encoding="utf-8")
            repo = PortfolioRepository(data_path=str(path))
            with pytest.raises(ValueError) as exc_info:
                repo.load()
            assert ".bak" in str(exc_info.value)
            assert (path.with_suffix(".json.bak")).exists()


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

class TestPrompts:
    def test_build_pm_prompt_with_holding(self):
        p = Portfolio(
            holdings={
                "002241.SZ": Holding(
                    ticker="002241.SZ",
                    name="歌尔股份",
                    shares=4500,
                    avg_cost=28.41,
                    market_price=25.37,
                    pnl_pct=-0.107,
                    weight=0.0959,
                ),
            }
        )
        prompt = build_pm_prompt("002241.SZ", p)
        assert "歌尔股份" in prompt
        assert "28.41" in prompt
        assert "-10.70%" in prompt
        assert "9.59%" in prompt

    def test_build_pm_prompt_no_holding(self):
        p = Portfolio()
        assert build_pm_prompt("UNKNOWN", p) == ""

    def test_build_risk_prompt_concentration_warning(self):
        p = Portfolio(
            holdings={
                "A": Holding(ticker="A", shares=100, avg_cost=10.0, weight=0.20, pnl_pct=-0.25),
            }
        )
        prompt = build_risk_prompt("A", p)
        assert "20.00%" in prompt
        assert "集中持仓" in prompt
        assert "亏损超过 20%" in prompt

    def test_build_trader_prompt_with_grid(self):
        p = Portfolio(
            holdings={
                "A": Holding(
                    ticker="A",
                    shares=100,
                    avg_cost=10.0,
                    market_price=12.0,
                    grid_strategy="网格宽度: +3%/-3%",
                ),
            }
        )
        prompt = build_trader_prompt("A", p)
        assert "网格策略" in prompt
        assert "+20.00%" in prompt  # price gap


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_legacy_holdings_dict(self):
        """Ensure legacy flat dict format still works via Holding.from_dict."""
        legacy = {
            "002241.SZ": {
                "shares": 4500.0,
                "avg_cost": 28.41,
                "market_price": 25.37,
                "pnl_pct": -0.107,
                "weight": 0.0959,
                "grid_strategy": None,
                "name": "",
            }
        }
        portfolio = Portfolio(
            holdings={t: Holding.from_dict(d, ticker=t) for t, d in legacy.items()}
        )
        assert portfolio.has_holding("002241.SZ")
        h = portfolio.get_holding("002241.SZ")
        assert h.shares == 4500.0
        assert h.pnl_pct == -0.107


# ---------------------------------------------------------------------------
# Sync integration (requires gws auth — marked as integration)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Validators extended
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestParseNumber:
    def test_parses_int(self):
        from tradingagents.portfolio.validators import _parse_number

        assert _parse_number(42) == 42.0

    def test_parses_float(self):
        from tradingagents.portfolio.validators import _parse_number

        assert _parse_number(3.14) == 3.14

    def test_parses_clean_string(self):
        from tradingagents.portfolio.validators import _parse_number

        assert _parse_number("123.45") == 123.45

    def test_strips_thousand_separators(self):
        from tradingagents.portfolio.validators import _parse_number

        assert _parse_number("1,234.56") == 1234.56

    def test_strips_chinese_thousand_separators(self):
        from tradingagents.portfolio.validators import _parse_number

        assert _parse_number("1，234.56") == 1234.56

    def test_strips_currency_symbols(self):
        from tradingagents.portfolio.validators import _parse_number

        assert _parse_number("$1,500.00") == 1500.0
        assert _parse_number("¥2,300.50") == 2300.5

    def test_raises_on_non_numeric_type(self):
        from tradingagents.portfolio.validators import _parse_number

        with pytest.raises(ValueError):
            _parse_number([1, 2, 3])


@pytest.mark.unit
class TestDeduplicateHoldings:
    def test_deduplicates_by_ticker(self):
        from tradingagents.portfolio.validators import deduplicate_holdings
        from tradingagents.portfolio.models import Holding

        h1 = Holding(ticker="AAPL", shares=100, avg_cost=150.0)
        h2 = Holding(ticker="AAPL", shares=200, avg_cost=155.0)
        h3 = Holding(ticker="MSFT", shares=50, avg_cost=300.0)

        result = deduplicate_holdings([h1, h2, h3])
        assert len(result) == 2
        assert result["AAPL"].shares == 200  # last occurrence wins
        assert result["MSFT"].shares == 50

    def test_skips_empty_ticker(self):
        from tradingagents.portfolio.validators import deduplicate_holdings
        from tradingagents.portfolio.models import Holding

        h1 = Holding(ticker="", shares=100, avg_cost=10.0)
        h2 = Holding(ticker="AAPL", shares=200, avg_cost=150.0)

        result = deduplicate_holdings([h1, h2])
        assert len(result) == 1
        assert "AAPL" in result

    def test_returns_empty_dict_for_empty_list(self):
        from tradingagents.portfolio.validators import deduplicate_holdings

        result = deduplicate_holdings([])
        assert result == {}


@pytest.mark.unit
class TestNormalizeTickerExtended:
    def test_shanghai_6_prefix(self):
        from tradingagents.portfolio.validators import normalize_ticker

        assert normalize_ticker("600519") == "600519.SS"

    def test_bj_prefix_not_supported(self):
        from tradingagents.portfolio.validators import normalize_ticker

        assert normalize_ticker("830123") == "830123"

    def test_numeric_0_prefix(self):
        from tradingagents.portfolio.validators import normalize_ticker

        assert normalize_ticker("000001") == "000001.SZ"

    def test_numeric_3_prefix(self):
        from tradingagents.portfolio.validators import normalize_ticker

        assert normalize_ticker("300999") == "300999.SZ"

    def test_returns_none_for_chinese_headers(self):
        from tradingagents.portfolio.validators import normalize_ticker

        assert normalize_ticker("合计") is None
        assert normalize_ticker("可用现金") is None
        assert normalize_ticker("N/A") is None
        assert normalize_ticker("n/a") is None

    def test_returns_none_for_empty_or_dash(self):
        from tradingagents.portfolio.validators import normalize_ticker

        assert normalize_ticker("") is None
        assert normalize_ticker("-") is None
        assert normalize_ticker("—") is None

    def test_preserves_exchange_qualified(self):
        from tradingagents.portfolio.validators import normalize_ticker

        assert normalize_ticker("HK1810") == "HK1810"
        assert normalize_ticker("BRK.B") == "BRK.B"


@pytest.mark.unit
class TestValidateHoldingExtended:
    def test_empty_ticker_returns_none(self):
        from tradingagents.portfolio.validators import validate_holding
        from tradingagents.portfolio.models import Holding

        h = Holding(ticker="", shares=100, avg_cost=10.0)
        assert validate_holding(h) is None

    def test_zero_shares_returns_none(self):
        from tradingagents.portfolio.validators import validate_holding
        from tradingagents.portfolio.models import Holding

        h = Holding(ticker="AAPL", shares=0, avg_cost=10.0)
        assert validate_holding(h) is None

    def test_negative_cost_returns_none(self):
        from tradingagents.portfolio.validators import validate_holding
        from tradingagents.portfolio.models import Holding

        h = Holding(ticker="AAPL", shares=100, avg_cost=-5.0)
        assert validate_holding(h) is None

    def test_valid_holding_returned(self):
        from tradingagents.portfolio.validators import validate_holding
        from tradingagents.portfolio.models import Holding

        h = Holding(ticker="AAPL", shares=100, avg_cost=150.0)
        assert validate_holding(h) is h


# ---------------------------------------------------------------------------
# Models extended
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTransactionModel:
    def test_roundtrip(self):
        from tradingagents.portfolio.models import Transaction

        t = Transaction(
            date="2026-01-15", ticker="002241.SZ", name="歌尔股份",
            price=28.41, action="买入", shares=500, fee=5.0,
            cash_change=-14205.0, tag="手动建仓",
        )
        d = t.to_dict()
        t2 = Transaction.from_dict(d)
        assert t2.date == "2026-01-15"
        assert t2.action == "买入"
        assert t2.shares == 500

    def test_to_dict_excludes_empty(self):
        from tradingagents.portfolio.models import Transaction

        t = Transaction(date="2026-01-15", ticker="AAPL", action="买入", shares=100, price=150.0)
        d = t.to_dict()
        assert "name" not in d
        assert "fee" not in d

    def test_from_dict_filters_invalid(self):
        from tradingagents.portfolio.models import Transaction

        t = Transaction.from_dict({"date": "2026-01-15", "ticker": "AAPL", "action": "买入", "shares": 100, "price": 150.0, "invalid_key": "x"})
        assert t.date == "2026-01-15"
        assert not hasattr(t, "invalid_key")


@pytest.mark.unit
class TestPortfolioExtended:
    def test_get_holding_returns_none(self):
        from tradingagents.portfolio.models import Portfolio

        p = Portfolio()
        assert p.get_holding("NONEXIST") is None

    def test_total_market_value(self):
        from tradingagents.portfolio.models import Holding, Portfolio

        p = Portfolio(holdings={
            "A": Holding(ticker="A", shares=100, avg_cost=10.0, market_price=15.0),
            "B": Holding(ticker="B", shares=200, avg_cost=5.0, market_price=6.0),
        })
        assert p.total_market_value() == 2700.0

    def test_total_market_value_falls_back_to_cost(self):
        from tradingagents.portfolio.models import Holding, Portfolio

        p = Portfolio(holdings={
            "A": Holding(ticker="A", shares=100, avg_cost=10.0),
        })
        assert p.total_market_value() == 1000.0

    def test_total_pnl(self):
        from tradingagents.portfolio.models import Holding, Portfolio

        p = Portfolio(holdings={
            "A": Holding(ticker="A", shares=100, avg_cost=10.0, market_price=12.0),
        })
        assert p.total_pnl() == 200.0

    def test_from_dict_with_transactions(self):
        from tradingagents.portfolio.models import Holding, Portfolio

        data = {
            "holdings": {"A": {"ticker": "A", "shares": 100, "avg_cost": 10.0}},
            "metadata": {"updated_at": "2026-01-01T00:00:00+00:00"},
            "summary": {"total_holdings": 1},
            "transactions": [
                {"date": "2026-01-15", "ticker": "A", "action": "买入", "shares": 100, "price": 10.0},
            ],
        }
        p = Portfolio.from_dict(data)
        assert len(p.transactions) == 1
        assert p.transactions[0].action == "买入"

    def test_roundtrip_with_transactions(self):
        from tradingagents.portfolio.models import Holding, Portfolio, PortfolioMetadata, Transaction

        p = Portfolio(
            holdings={"A": Holding(ticker="A", shares=100, avg_cost=10.0)},
            metadata=PortfolioMetadata(updated_at="2026-01-01T00:00:00+00:00"),
            transactions=[Transaction(date="2026-01-15", ticker="A", action="买入", shares=100, price=10.0)],
        )
        d = p.to_dict()
        p2 = Portfolio.from_dict(d)
        assert len(p2.transactions) == 1


@pytest.mark.unit
class TestPortfolioRepositoryExtended:
    def test_default_path(self):
        from tradingagents.portfolio.repository import PortfolioRepository

        repo = PortfolioRepository()
        assert "tradingagents_portfolio.json" in str(repo.path)

    def test_custom_path(self):
        from tradingagents.portfolio.repository import PortfolioRepository

        repo = PortfolioRepository(data_path="/tmp/custom.json")
        assert str(repo.path) == "/tmp/custom.json"

    def test_exists_returns_false_for_missing(self):
        import tempfile
        from tradingagents.portfolio.repository import PortfolioRepository

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = PortfolioRepository(data_path=tmpdir + "/missing.json")
            assert not repo.exists()

    def test_get_mtime_returns_none_for_missing(self):
        import tempfile
        from tradingagents.portfolio.repository import PortfolioRepository

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = PortfolioRepository(data_path=tmpdir + "/missing.json")
            assert repo.get_mtime() is None

    def test_save_atomic(self):
        import os
        import tempfile
        from tradingagents.portfolio.models import Holding, Portfolio
        from tradingagents.portfolio.repository import PortfolioRepository

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "portfolio.json")
            repo = PortfolioRepository(data_path=path)
            p = Portfolio(holdings={"A": Holding(ticker="A", shares=100, avg_cost=10.0)})
            repo.save(p)
            assert os.path.exists(path)
            # No .tmp file left behind
            assert not os.path.exists(path + ".tmp")

    def test_get_holding_convenience(self):
        import json
        import os
        import tempfile
        from tradingagents.portfolio.models import Holding, Portfolio
        from tradingagents.portfolio.repository import PortfolioRepository

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "portfolio.json")
            repo = PortfolioRepository(data_path=path)
            p = Portfolio(holdings={"A": Holding(ticker="A", shares=100, avg_cost=10.0)})
            repo.save(p)
            h = repo.get_holding("A")
            assert h["shares"] == 100
            assert repo.get_holding("B") is None


@pytest.mark.integration
class TestPortfolioSyncIntegration:
    def test_sync_from_gsheet(self):
        """Sync from a mocked Google Sheet response."""
        from tradingagents.portfolio import PortfolioSyncService

        sheet_id = "1g8EqjG8dVVVmH9Tq7Wq8UkXP72T7hoXZVP1cvqZz9g4"
        sync = PortfolioSyncService(sheet_id=sheet_id, worksheet="total")

        mock_rows = [
            ["代码", "资产名称", "持仓成本", "持仓数量", "现价", "投入本金 (元)", "盈亏率", "仓位占比", "网格策略"],
            ["600519", "贵州茅台", "1500.00", "100", "1600.00", "150000.00", "6.67%", "50.00%", ""],
            ["002241", "歌尔股份", "28.41", "4500", "25.37", "127845.00", "-10.70%", "9.59%", "网格宽度: +3%/-3%"],
            ["合计", "", "", "", "", "", "", "", ""],
        ]

        with patch.object(
            sync, "_fetch_from_gsheet", return_value=mock_rows
        ):
            portfolio = sync.sync()

        assert len(portfolio.holdings) == 2
        assert portfolio.metadata.source_type == "google_sheet"
        assert portfolio.summary["total_holdings"] == 2

        # Verify A-share suffix normalization
        assert "600519.SS" in portfolio.holdings
        assert "002241.SZ" in portfolio.holdings

        # Verify numeric parsing (no commas left)
        h1 = portfolio.holdings["600519.SS"]
        assert isinstance(h1.shares, float)
        assert h1.shares == 100.0
        assert isinstance(h1.avg_cost, float)
        assert h1.avg_cost == 1500.0
        assert h1.market_price == 1600.0
        assert h1.pnl_pct == 0.0667
        assert h1.weight == 0.5

        h2 = portfolio.holdings["002241.SZ"]
        assert h2.shares == 4500.0
        assert h2.avg_cost == 28.41
        assert h2.grid_strategy == "网格宽度: +3%/-3%"


# =========================================================================
# Edge-case tests merged from test_remaining_coverage.py
# =========================================================================


@pytest.mark.unit
class PortfolioRepositoryGetMtimeTests(_TempDirMixin, unittest.TestCase):
    """Line 46: get_mtime with existing file."""

    def test_get_mtime_returns_datetime(self):
        p = self._tmp / "portfolio.json"
        p.write_text('{}', encoding="utf-8")
        repo = PortfolioRepository(data_path=str(p))
        mtime = repo.get_mtime()
        self.assertIsInstance(mtime, datetime)


@pytest.mark.unit
class PortfolioRepositoryLoadEdgeCases(_TempDirMixin, unittest.TestCase):
    """Lines 56, 64-68: FileNotFoundError, JSONDecodeError with backup."""

    def test_load_raises_on_missing_file(self):
        repo = PortfolioRepository(data_path=str(self._tmp / "nonexistent.json"))
        with self.assertRaises(FileNotFoundError):
            repo.load()

    def test_load_backups_corrupted_file(self):
        p = self._tmp / "corrupt.json"
        p.write_text("{bad json", encoding="utf-8")
        repo = PortfolioRepository(data_path=str(p))
        with self.assertRaises(ValueError):
            repo.load()
        self.assertTrue(p.with_suffix(".json.bak").exists())


@pytest.mark.unit
class PortfolioRepositorySaveFailureTests(_TempDirMixin, unittest.TestCase):
    """Lines 94-98: save temp file cleanup on failure."""

    def test_save_cleans_temp_on_failure(self):
        p = self._tmp / "portfolio.json"
        repo = PortfolioRepository(data_path=str(p))
        portfolio = Portfolio()

        with patch("builtins.open") as mock_open:
            mock_open.side_effect = OSError("write failed")
            with self.assertRaises(OSError):
                repo.save(portfolio)

        temp_file = p.with_suffix(".tmp")
        self.assertFalse(temp_file.exists())

    def test_save_cleans_temp_on_replace_failure(self):
        """Line 97: unlink called when temp file exists but os.replace fails."""
        p = self._tmp / "portfolio.json"
        repo = PortfolioRepository(data_path=str(p))
        portfolio = Portfolio()

        with patch("os.replace", side_effect=OSError("replace failed")):
            with self.assertRaises(OSError):
                repo.save(portfolio)

        temp_file = p.with_suffix(".tmp")
        self.assertFalse(temp_file.exists())


@pytest.mark.unit
class PortfolioRepositoryGetHoldingEdgeTests(unittest.TestCase):
    """Lines 106-107: get_holding with FileNotFoundError returns None."""

    def test_get_holding_file_not_found_returns_none(self):
        repo = PortfolioRepository(data_path="/nonexistent/path.json")
        result = repo.get_holding("AAPL")
        self.assertIsNone(result)
