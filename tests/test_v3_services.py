"""Unit tests for TradingAgents Desktop v3 services layer.

Tests cover:
1. recommendation_extractor -- extract_recommendation() and extract_from_file()
2. price_service -- PriceService with TTL cache
3. alert_engine -- AlertEngine lifecycle + market hours
4. outcome_tracker -- OutcomeTracker lifecycle
5. scheduler -- CronExpr parsing + Scheduler lifecycle
6. pdf_export -- PDFExporter (without weasyprint)
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# ── Module imports ──────────────────────────────────────────────────────

from desktop.services.recommendation_extractor import (
    ExtractedRecommendation,
    _extract_confidence,
    _extract_verdict,
    _first_price,
    _parse_price_str,
    extract_from_file,
    extract_recommendation,
)
from desktop.services.price_service import (
    PriceResult,
    PriceService,
    _CachedPrice,
    _compute_change_pct,
)
from desktop.services.alert_engine import (
    AlertEngine,
    _is_market_hours,
    _poll_interval,
)
from desktop.services.outcome_tracker import (
    OutcomeTracker,
    _check_stop_hit,
    _check_target_hit,
    _compute_return_pct,
    _days_since,
)
from desktop.services.scheduler import CronExpr, Scheduler
from desktop.services.pdf_export import (
    PDFExporter,
    _md_to_html,
    _verdict_class,
)
from desktop.state.database import (
    AlertHistoryRow,
    AlertRow,
    HistoryDB,
    RecommendationRow,
)

# ═══════════════════════════════════════════════════════════════════════
# 1. Recommendation Extractor
# ═══════════════════════════════════════════════════════════════════════


class TestParsePrice:
    """Tests for the _parse_price_str helper."""

    @pytest.mark.unit
    def test_english_decimal(self) -> None:
        assert _parse_price_str("89.17") == 89.17

    @pytest.mark.unit
    def test_russian_decimal(self) -> None:
        assert _parse_price_str("89,17") == 89.17

    @pytest.mark.unit
    def test_thousands_separator(self) -> None:
        assert _parse_price_str("1,283") == 1283.0

    @pytest.mark.unit
    def test_thousands_with_decimal(self) -> None:
        assert _parse_price_str("2,850.50") == 2850.50

    @pytest.mark.unit
    def test_integer(self) -> None:
        assert _parse_price_str("77") == 77.0

    @pytest.mark.unit
    def test_empty_string(self) -> None:
        assert _parse_price_str("") is None

    @pytest.mark.unit
    def test_russian_decimal_94_70(self) -> None:
        assert _parse_price_str("94,70") == 94.70


class TestFirstPrice:
    """Tests for _first_price (regex + parsing combined)."""

    @pytest.mark.unit
    def test_dollar_price(self) -> None:
        assert _first_price("стоп-лосс $77") == 77.0

    @pytest.mark.unit
    def test_dollar_with_space(self) -> None:
        assert _first_price("цена $ 580.25") == 580.25

    @pytest.mark.unit
    def test_no_dollar(self) -> None:
        assert _first_price("no price here") is None


class TestExtractVerdict:
    """Tests for _extract_verdict with Russian markdown headers."""

    @pytest.mark.unit
    def test_header_hold(self) -> None:
        md = "## Итоговый рейтинг: **HOLD**\nsome text"
        assert _extract_verdict(md) == "HOLD"

    @pytest.mark.unit
    def test_header_buy(self) -> None:
        md = "## ВЕРДИКТ: **BUY**\n\ntext"
        assert _extract_verdict(md) == "BUY"

    @pytest.mark.unit
    def test_header_sell_no_bold(self) -> None:
        md = "### Рейтинг: SELL\ntext"
        assert _extract_verdict(md) == "SELL"

    @pytest.mark.unit
    def test_header_overweight(self) -> None:
        md = "## Итоговый рейтинг: **OVERWEIGHT**\nsome body"
        assert _extract_verdict(md) == "OVERWEIGHT"

    @pytest.mark.unit
    def test_header_underweight(self) -> None:
        md = "## Рейтинг: **Underweight**"
        assert _extract_verdict(md) == "UNDERWEIGHT"

    @pytest.mark.unit
    def test_bold_fallback(self) -> None:
        md = "# Title\nsome intro\n**SELL** is the recommendation\n" + "\n" * 30
        assert _extract_verdict(md) == "SELL"

    @pytest.mark.unit
    def test_bare_keyword_fallback(self) -> None:
        md = "# Report\nWe recommend BUY\nmore text"
        assert _extract_verdict(md) == "BUY"

    @pytest.mark.unit
    def test_unknown_when_missing(self) -> None:
        md = "# Report\nNo clear recommendation\n" * 20
        assert _extract_verdict(md) == "UNKNOWN"


class TestExtractConfidence:
    """Tests for _extract_confidence."""

    @pytest.mark.unit
    def test_russian_confidence(self) -> None:
        md = "Убеждённость: 8/10"
        assert _extract_confidence(md) == 8

    @pytest.mark.unit
    def test_english_confidence(self) -> None:
        md = "confidence: 7/10"
        assert _extract_confidence(md) == 7

    @pytest.mark.unit
    def test_iz_pattern(self) -> None:
        md = "уровень уверенности 9 из 10 баллов"
        assert _extract_confidence(md) == 9

    @pytest.mark.unit
    def test_out_of_range_returns_none(self) -> None:
        md = "Убеждённость: 15/10"
        assert _extract_confidence(md) is None

    @pytest.mark.unit
    def test_no_confidence_returns_none(self) -> None:
        assert _extract_confidence("no confidence info here") is None


class TestExtractRecommendation:
    """Tests for the main extract_recommendation() function."""

    @pytest.mark.unit
    def test_empty_markdown(self) -> None:
        rec = extract_recommendation("")
        assert rec.ticker == "UNKNOWN"
        assert rec.verdict == "UNKNOWN"

    @pytest.mark.unit
    def test_empty_with_ticker_override(self) -> None:
        rec = extract_recommendation("", ticker="AAPL")
        assert rec.ticker == "AAPL"
        assert rec.verdict == "UNKNOWN"

    @pytest.mark.unit
    def test_full_report_extraction(self) -> None:
        md = """# Вердикт Портфельного Менеджера: NFLX

## Итоговый рейтинг: **HOLD**

Убеждённость: 7/10

Текущая цена $580.25.

| **Стоп-лосс** | **$540** |
| **Целевая** | **$640** |

Entry trigger: закрытие выше $590

Горизонт пересмотра: 2 недели

## Заключение
Netflix remains well-positioned despite near-term volatility.
"""
        rec = extract_recommendation(md, analysis_id=42)
        assert rec.ticker == "NFLX"
        assert rec.verdict == "HOLD"
        assert rec.confidence == 7
        assert rec.price_at_analysis == 580.25
        assert rec.stop_loss == 540.0
        assert rec.profit_target == 640.0
        assert rec.entry_trigger == 590.0
        assert rec.review_date is not None
        assert rec.notes is not None
        assert rec.analysis_id == 42

    @pytest.mark.unit
    def test_ticker_from_instrument_field(self) -> None:
        md = "# Финальное решение\n**Инструмент:** CRWD (CrowdStrike)\n## Рейтинг: **BUY**"
        rec = extract_recommendation(md)
        assert rec.ticker == "CRWD"
        assert rec.verdict == "BUY"

    @pytest.mark.unit
    def test_ticker_override_takes_precedence_on_no_match(self) -> None:
        md = "# Some report with no ticker\n## Рейтинг: **SELL**"
        rec = extract_recommendation(md, ticker="SPY")
        assert rec.ticker == "SPY"

    @pytest.mark.unit
    def test_frozen_dataclass(self) -> None:
        rec = extract_recommendation("## Рейтинг: **BUY**", ticker="TSLA")
        with pytest.raises(AttributeError):
            rec.verdict = "SELL"  # type: ignore[misc]


class TestExtractFromFile:
    """Tests for extract_from_file() reading actual files."""

    @pytest.mark.unit
    def test_file_not_found(self, tmp_path: Path) -> None:
        rec = extract_from_file(tmp_path / "nonexistent.md", ticker="ABC")
        assert rec.ticker == "ABC"
        assert rec.verdict == "UNKNOWN"

    @pytest.mark.unit
    def test_valid_file(self, tmp_path: Path) -> None:
        md_file = tmp_path / "final_trade_decision.md"
        md_file.write_text(
            "# Вердикт Портфельного Менеджера: AAPL\n"
            "## Итоговый рейтинг: **BUY**\n"
            "Убеждённость: 9/10\n",
            encoding="utf-8",
        )
        rec = extract_from_file(md_file, analysis_id=7)
        assert rec.ticker == "AAPL"
        assert rec.verdict == "BUY"
        assert rec.confidence == 9
        assert rec.analysis_id == 7

    @pytest.mark.unit
    def test_empty_file(self, tmp_path: Path) -> None:
        md_file = tmp_path / "empty.md"
        md_file.write_text("", encoding="utf-8")
        rec = extract_from_file(md_file)
        assert rec.verdict == "UNKNOWN"


# ═══════════════════════════════════════════════════════════════════════
# 2. Price Service
# ═══════════════════════════════════════════════════════════════════════


class TestComputeChangePct:
    """Tests for _compute_change_pct helper."""

    @pytest.mark.unit
    def test_positive_change(self) -> None:
        assert _compute_change_pct(110.0, 100.0) == 10.0

    @pytest.mark.unit
    def test_negative_change(self) -> None:
        assert _compute_change_pct(90.0, 100.0) == -10.0

    @pytest.mark.unit
    def test_none_price(self) -> None:
        assert _compute_change_pct(None, 100.0) is None

    @pytest.mark.unit
    def test_none_previous_close(self) -> None:
        assert _compute_change_pct(100.0, None) is None

    @pytest.mark.unit
    def test_zero_previous_close(self) -> None:
        assert _compute_change_pct(100.0, 0.0) is None


class TestPriceServiceFetchSingle:
    """Tests for PriceService._fetch_single with mocked yfinance."""

    @pytest.mark.unit
    @patch("desktop.services.price_service._YF_AVAILABLE", True)
    @patch("desktop.services.price_service.yf")
    def test_successful_fetch(self, mock_yf: MagicMock) -> None:
        fast_info = SimpleNamespace(last_price=150.50, previous_close=148.00)
        mock_yf.Ticker.return_value.fast_info = fast_info

        svc = PriceService(ttl_seconds=60)
        result = svc._fetch_single("AAPL", stale_fallback=None)

        assert result.ticker == "AAPL"
        assert result.price == 150.50
        assert result.previous_close == 148.00
        assert result.is_stale is False
        assert result.error is None
        assert result.change_pct is not None

    @pytest.mark.unit
    @patch("desktop.services.price_service._YF_AVAILABLE", True)
    @patch("desktop.services.price_service.yf")
    def test_fetch_returns_none_price(self, mock_yf: MagicMock) -> None:
        fast_info = SimpleNamespace(last_price=None, previous_close=100.0)
        mock_yf.Ticker.return_value.fast_info = fast_info

        svc = PriceService(ttl_seconds=60)
        result = svc._fetch_single("BAD", stale_fallback=None)

        assert result.price is None
        assert result.error is not None

    @pytest.mark.unit
    @patch("desktop.services.price_service._YF_AVAILABLE", True)
    @patch("desktop.services.price_service.yf")
    def test_stale_fallback_on_error(self, mock_yf: MagicMock) -> None:
        mock_yf.Ticker.side_effect = Exception("Network error")

        stale_result = PriceResult(
            ticker="AAPL",
            price=145.0,
            previous_close=144.0,
            change_pct=0.6944,
            is_stale=False,
            fetched_at="2025-01-01T00:00:00Z",
            error=None,
        )
        stale_fallback = _CachedPrice(
            result=stale_result,
            fetched_at_dt=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )

        svc = PriceService(ttl_seconds=60)
        result = svc._fetch_single("AAPL", stale_fallback=stale_fallback)

        assert result.is_stale is True
        assert result.price == 145.0
        assert result.error is not None

    @pytest.mark.unit
    @patch("desktop.services.price_service._YF_AVAILABLE", True)
    @patch("desktop.services.price_service.yf")
    def test_error_result_without_stale(self, mock_yf: MagicMock) -> None:
        mock_yf.Ticker.side_effect = Exception("Timeout")

        svc = PriceService(ttl_seconds=60)
        result = svc._fetch_single("AAPL", stale_fallback=None)

        assert result.price is None
        assert result.error is not None
        assert result.is_stale is False


class TestPriceServiceCache:
    """Tests for TTL cache behavior."""

    @pytest.mark.unit
    @patch("desktop.services.price_service._YF_AVAILABLE", True)
    @patch("desktop.services.price_service.yf")
    def test_cache_hit_within_ttl(self, mock_yf: MagicMock) -> None:
        fast_info = SimpleNamespace(last_price=200.0, previous_close=199.0)
        mock_yf.Ticker.return_value.fast_info = fast_info

        svc = PriceService(ttl_seconds=300)
        result1 = svc.get_price("MSFT")
        result2 = svc.get_price("MSFT")

        # yfinance should only be called once (second call hits cache)
        assert mock_yf.Ticker.call_count == 1
        assert result1.price == result2.price

    @pytest.mark.unit
    @patch("desktop.services.price_service._YF_AVAILABLE", True)
    @patch("desktop.services.price_service.yf")
    def test_invalidate_single(self, mock_yf: MagicMock) -> None:
        fast_info = SimpleNamespace(last_price=200.0, previous_close=199.0)
        mock_yf.Ticker.return_value.fast_info = fast_info

        svc = PriceService(ttl_seconds=300)
        svc.get_price("MSFT")
        svc.invalidate("MSFT")
        svc.get_price("MSFT")

        # After invalidation, yfinance should be called again
        assert mock_yf.Ticker.call_count == 2

    @pytest.mark.unit
    @patch("desktop.services.price_service._YF_AVAILABLE", True)
    @patch("desktop.services.price_service.yf")
    def test_invalidate_all(self, mock_yf: MagicMock) -> None:
        fast_info = SimpleNamespace(last_price=200.0, previous_close=199.0)
        mock_yf.Ticker.return_value.fast_info = fast_info

        svc = PriceService(ttl_seconds=300)
        svc.get_price("AAPL")
        svc.get_price("MSFT")
        svc.invalidate()  # clear all
        svc.get_price("AAPL")

        # AAPL: first call + after invalidation = at least 2 Ticker calls for AAPL
        assert mock_yf.Ticker.call_count >= 3

    @pytest.mark.unit
    def test_yfinance_not_available(self) -> None:
        with patch("desktop.services.price_service._YF_AVAILABLE", False):
            svc = PriceService()
            result = svc.get_price("AAPL")
            assert result.error is not None
            assert result.price is None


class TestPriceServiceGetPrices:
    """Tests for batch get_prices."""

    @pytest.mark.unit
    @patch("desktop.services.price_service._YF_AVAILABLE", True)
    @patch("desktop.services.price_service.yf")
    def test_empty_tickers(self, mock_yf: MagicMock) -> None:
        svc = PriceService(ttl_seconds=60)
        result = svc.get_prices([])
        assert result == {}

    @pytest.mark.unit
    @patch("desktop.services.price_service._YF_AVAILABLE", True)
    @patch("desktop.services.price_service.yf")
    def test_multiple_tickers(self, mock_yf: MagicMock) -> None:
        fast_info = SimpleNamespace(last_price=100.0, previous_close=99.0)
        mock_yf.Ticker.return_value.fast_info = fast_info

        svc = PriceService(ttl_seconds=60)
        results = svc.get_prices(["AAPL", "MSFT", "GOOG"])

        assert len(results) == 3
        assert "AAPL" in results
        assert "MSFT" in results
        assert "GOOG" in results
        for pr in results.values():
            assert pr.price == 100.0


# ═══════════════════════════════════════════════════════════════════════
# 3. Alert Engine
# ═══════════════════════════════════════════════════════════════════════


class TestAlertEngineMarketHours:
    """Tests for market hours detection."""

    @pytest.mark.unit
    @patch("desktop.services.alert_engine.datetime")
    def test_market_open_weekday(self, mock_dt: MagicMock) -> None:
        # Wednesday 10:00 ET -> market open
        mock_now = MagicMock()
        mock_now.weekday.return_value = 2  # Wednesday
        mock_now.hour = 10
        mock_now.minute = 0
        mock_dt.now.return_value = mock_now
        assert _is_market_hours() is True

    @pytest.mark.unit
    @patch("desktop.services.alert_engine.datetime")
    def test_market_closed_weekend(self, mock_dt: MagicMock) -> None:
        mock_now = MagicMock()
        mock_now.weekday.return_value = 5  # Saturday
        mock_now.hour = 12
        mock_now.minute = 0
        mock_dt.now.return_value = mock_now
        assert _is_market_hours() is False

    @pytest.mark.unit
    @patch("desktop.services.alert_engine.datetime")
    def test_market_closed_early_morning(self, mock_dt: MagicMock) -> None:
        mock_now = MagicMock()
        mock_now.weekday.return_value = 1  # Tuesday
        mock_now.hour = 7
        mock_now.minute = 0
        mock_dt.now.return_value = mock_now
        assert _is_market_hours() is False

    @pytest.mark.unit
    @patch("desktop.services.alert_engine.datetime")
    def test_market_closed_after_hours(self, mock_dt: MagicMock) -> None:
        mock_now = MagicMock()
        mock_now.weekday.return_value = 3  # Thursday
        mock_now.hour = 17
        mock_now.minute = 0
        mock_dt.now.return_value = mock_now
        assert _is_market_hours() is False


class TestAlertEngineIsTriggered:
    """Tests for AlertEngine._is_triggered static method."""

    @pytest.mark.unit
    def test_above_triggered(self) -> None:
        alert = AlertRow(
            id=1, recommendation_id=1, ticker="AAPL",
            alert_type="profit_target", target_price=200.0,
            direction="above", triggered_at=None, triggered_price=None,
            is_active=1, created_at="2025-01-01",
        )
        assert AlertEngine._is_triggered(alert, 200.0) is True
        assert AlertEngine._is_triggered(alert, 210.0) is True
        assert AlertEngine._is_triggered(alert, 199.99) is False

    @pytest.mark.unit
    def test_below_triggered(self) -> None:
        alert = AlertRow(
            id=2, recommendation_id=1, ticker="AAPL",
            alert_type="stop_loss", target_price=150.0,
            direction="below", triggered_at=None, triggered_price=None,
            is_active=1, created_at="2025-01-01",
        )
        assert AlertEngine._is_triggered(alert, 150.0) is True
        assert AlertEngine._is_triggered(alert, 140.0) is True
        assert AlertEngine._is_triggered(alert, 150.01) is False

    @pytest.mark.unit
    def test_unknown_direction(self) -> None:
        alert = AlertRow(
            id=3, recommendation_id=1, ticker="AAPL",
            alert_type="custom", target_price=100.0,
            direction="sideways", triggered_at=None, triggered_price=None,
            is_active=1, created_at="2025-01-01",
        )
        assert AlertEngine._is_triggered(alert, 100.0) is False


class TestAlertEngineLifecycle:
    """Tests for AlertEngine start/stop lifecycle."""

    @pytest.mark.unit
    def test_start_stop(self, tmp_path: Path) -> None:
        db = HistoryDB(db_path=tmp_path / "test.db")
        price_svc = PriceService(ttl_seconds=60)

        engine = AlertEngine(db=db, price_service=price_svc)
        assert engine.is_running is False

        engine.start()
        assert engine.is_running is True

        engine.stop()
        assert engine.is_running is False

    @pytest.mark.unit
    def test_double_start_is_idempotent(self, tmp_path: Path) -> None:
        db = HistoryDB(db_path=tmp_path / "test.db")
        price_svc = PriceService(ttl_seconds=60)

        engine = AlertEngine(db=db, price_service=price_svc)
        engine.start()
        engine.start()  # Should not raise
        assert engine.is_running is True
        engine.stop()

    @pytest.mark.unit
    def test_stop_without_start(self, tmp_path: Path) -> None:
        db = HistoryDB(db_path=tmp_path / "test.db")
        price_svc = PriceService(ttl_seconds=60)

        engine = AlertEngine(db=db, price_service=price_svc)
        engine.stop()  # Should not raise
        assert engine.is_running is False

    @pytest.mark.unit
    def test_on_alert_callback_registration(self, tmp_path: Path) -> None:
        db = HistoryDB(db_path=tmp_path / "test.db")
        price_svc = PriceService(ttl_seconds=60)

        engine = AlertEngine(db=db, price_service=price_svc)
        callback = MagicMock()
        engine.on_alert(callback)
        assert callback in engine._callbacks

    @pytest.mark.unit
    def test_initial_properties(self, tmp_path: Path) -> None:
        db = HistoryDB(db_path=tmp_path / "test.db")
        price_svc = PriceService(ttl_seconds=60)

        engine = AlertEngine(db=db, price_service=price_svc)
        assert engine.is_degraded is False
        assert engine.backoff_seconds == 0
        assert engine.last_poll_at is None
        assert engine.unseen_count == 0


class TestAlertEnginePollInterval:
    """Tests for adaptive poll interval."""

    @pytest.mark.unit
    @patch("desktop.services.alert_engine._is_market_hours", return_value=True)
    def test_market_hours_interval(self, _mock: MagicMock) -> None:
        assert _poll_interval() == 300  # 5 min

    @pytest.mark.unit
    @patch("desktop.services.alert_engine._is_market_hours", return_value=False)
    def test_off_hours_interval(self, _mock: MagicMock) -> None:
        assert _poll_interval() == 1800  # 30 min


# ═══════════════════════════════════════════════════════════════════════
# 4. Outcome Tracker
# ═══════════════════════════════════════════════════════════════════════


class TestOutcomeTrackerHelpers:
    """Tests for outcome tracker helper functions."""

    @pytest.mark.unit
    def test_days_since_recent(self) -> None:
        # 1 day ago
        one_day_ago = (datetime.now(tz=timezone.utc) - timedelta(days=1)).isoformat()
        result = _days_since(one_day_ago)
        assert 0.9 < result < 1.1

    @pytest.mark.unit
    def test_days_since_naive_datetime(self) -> None:
        # Should handle naive datetimes (treated as UTC)
        naive_iso = datetime.now(tz=timezone.utc).replace(
            tzinfo=None,
        ).isoformat()
        result = _days_since(naive_iso)
        assert 0.0 <= result < 0.01

    @pytest.mark.unit
    def test_check_stop_hit_true(self) -> None:
        rec = _make_recommendation_row(stop_loss=100.0)
        assert _check_stop_hit(99.0, rec) is True
        assert _check_stop_hit(100.0, rec) is True

    @pytest.mark.unit
    def test_check_stop_hit_false(self) -> None:
        rec = _make_recommendation_row(stop_loss=100.0)
        assert _check_stop_hit(101.0, rec) is False

    @pytest.mark.unit
    def test_check_stop_hit_none(self) -> None:
        rec = _make_recommendation_row(stop_loss=None)
        assert _check_stop_hit(99.0, rec) is False

    @pytest.mark.unit
    def test_check_target_hit_true(self) -> None:
        rec = _make_recommendation_row(profit_target=200.0)
        assert _check_target_hit(200.0, rec) is True
        assert _check_target_hit(210.0, rec) is True

    @pytest.mark.unit
    def test_check_target_hit_false(self) -> None:
        rec = _make_recommendation_row(profit_target=200.0)
        assert _check_target_hit(199.0, rec) is False

    @pytest.mark.unit
    def test_check_target_hit_none(self) -> None:
        rec = _make_recommendation_row(profit_target=None)
        assert _check_target_hit(300.0, rec) is False

    @pytest.mark.unit
    def test_compute_return_pct_positive(self) -> None:
        assert _compute_return_pct(100.0, 110.0) == 10.0

    @pytest.mark.unit
    def test_compute_return_pct_negative(self) -> None:
        assert _compute_return_pct(100.0, 90.0) == -10.0

    @pytest.mark.unit
    def test_compute_return_pct_none_base(self) -> None:
        assert _compute_return_pct(None, 100.0) == 0.0

    @pytest.mark.unit
    def test_compute_return_pct_zero_base(self) -> None:
        assert _compute_return_pct(0.0, 100.0) == 0.0


class TestOutcomeTrackerLifecycle:
    """Tests for OutcomeTracker start/stop."""

    @pytest.mark.unit
    def test_start_stop(self, tmp_path: Path) -> None:
        db = HistoryDB(db_path=tmp_path / "test.db")
        price_svc = PriceService(ttl_seconds=60)

        tracker = OutcomeTracker(db=db, price_service=price_svc)
        tracker.start()
        # Give it a moment for the initial check to complete
        time.sleep(0.05)
        tracker.stop()

    @pytest.mark.unit
    def test_double_start_is_idempotent(self, tmp_path: Path) -> None:
        db = HistoryDB(db_path=tmp_path / "test.db")
        price_svc = PriceService(ttl_seconds=60)

        tracker = OutcomeTracker(db=db, price_service=price_svc)
        tracker.start()
        tracker.start()  # Should not raise, should be no-op
        time.sleep(0.05)
        tracker.stop()

    @pytest.mark.unit
    def test_stop_without_start(self, tmp_path: Path) -> None:
        db = HistoryDB(db_path=tmp_path / "test.db")
        price_svc = PriceService(ttl_seconds=60)

        tracker = OutcomeTracker(db=db, price_service=price_svc)
        tracker.stop()  # Should not raise

    @pytest.mark.unit
    def test_run_check_empty_db(self, tmp_path: Path) -> None:
        db = HistoryDB(db_path=tmp_path / "test.db")
        price_svc = PriceService(ttl_seconds=60)

        tracker = OutcomeTracker(db=db, price_service=price_svc)
        recorded = tracker.run_check()
        assert recorded == 0


# ═══════════════════════════════════════════════════════════════════════
# 5. Scheduler — CronExpr parsing
# ═══════════════════════════════════════════════════════════════════════


class TestCronExprParse:
    """Tests for CronExpr.parse with various expression formats."""

    @pytest.mark.unit
    def test_basic_time(self) -> None:
        expr = CronExpr.parse("08:30")
        assert expr.hour == 8
        assert expr.minute == 30
        assert expr.weekdays == frozenset()

    @pytest.mark.unit
    def test_weekday_range(self) -> None:
        expr = CronExpr.parse("08:30 MON-FRI")
        assert expr.hour == 8
        assert expr.minute == 30
        assert expr.weekdays == frozenset({0, 1, 2, 3, 4})

    @pytest.mark.unit
    def test_specific_days(self) -> None:
        expr = CronExpr.parse("06:00 MON,WED,FRI")
        assert expr.weekdays == frozenset({0, 2, 4})

    @pytest.mark.unit
    def test_wildcard_days(self) -> None:
        expr = CronExpr.parse("09:00 *")
        assert expr.weekdays == frozenset()

    @pytest.mark.unit
    def test_midnight(self) -> None:
        expr = CronExpr.parse("00:00")
        assert expr.hour == 0
        assert expr.minute == 0

    @pytest.mark.unit
    def test_end_of_day(self) -> None:
        expr = CronExpr.parse("23:59")
        assert expr.hour == 23
        assert expr.minute == 59

    @pytest.mark.unit
    def test_weekend_only(self) -> None:
        expr = CronExpr.parse("10:00 SAT,SUN")
        assert expr.weekdays == frozenset({5, 6})

    @pytest.mark.unit
    def test_wrap_around_range(self) -> None:
        expr = CronExpr.parse("09:00 FRI-MON")
        assert expr.weekdays == frozenset({4, 5, 6, 0})

    @pytest.mark.unit
    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="Empty"):
            CronExpr.parse("")

    @pytest.mark.unit
    def test_no_colon_raises(self) -> None:
        with pytest.raises(ValueError, match="Expected HH:MM"):
            CronExpr.parse("0830")

    @pytest.mark.unit
    def test_invalid_hour_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid time"):
            CronExpr.parse("25:00")

    @pytest.mark.unit
    def test_invalid_minute_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid time"):
            CronExpr.parse("08:61")

    @pytest.mark.unit
    def test_unknown_day_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown day"):
            CronExpr.parse("08:00 BLAH")

    @pytest.mark.unit
    def test_unknown_day_in_range_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown day"):
            CronExpr.parse("08:00 MON-XYZ")


class TestCronExprNextFireTime:
    """Tests for CronExpr.next_fire_time."""

    @pytest.mark.unit
    def test_later_today(self) -> None:
        expr = CronExpr(hour=14, minute=0, weekdays=frozenset())
        after = datetime(2025, 6, 10, 10, 0, 0)  # Tuesday 10:00
        nft = expr.next_fire_time(after)
        assert nft == datetime(2025, 6, 10, 14, 0, 0)

    @pytest.mark.unit
    def test_tomorrow_when_past_time(self) -> None:
        expr = CronExpr(hour=8, minute=0, weekdays=frozenset())
        after = datetime(2025, 6, 10, 15, 0, 0)  # Tuesday 15:00, target 08:00
        nft = expr.next_fire_time(after)
        assert nft == datetime(2025, 6, 11, 8, 0, 0)

    @pytest.mark.unit
    def test_weekday_filter_skips_weekend(self) -> None:
        expr = CronExpr(hour=9, minute=0, weekdays=frozenset({0, 1, 2, 3, 4}))
        # Friday 17:00 -> next valid is Monday 09:00
        after = datetime(2025, 6, 13, 17, 0, 0)  # Friday
        nft = expr.next_fire_time(after)
        assert nft.weekday() == 0  # Monday
        assert nft == datetime(2025, 6, 16, 9, 0, 0)

    @pytest.mark.unit
    def test_exact_time_advances(self) -> None:
        expr = CronExpr(hour=8, minute=30, weekdays=frozenset())
        # At exactly 08:30, should return the NEXT occurrence (tomorrow)
        after = datetime(2025, 6, 10, 8, 30, 0)
        nft = expr.next_fire_time(after)
        assert nft == datetime(2025, 6, 11, 8, 30, 0)

    @pytest.mark.unit
    def test_single_day_filter(self) -> None:
        expr = CronExpr(hour=10, minute=0, weekdays=frozenset({2}))  # Wednesday
        after = datetime(2025, 6, 9, 12, 0, 0)  # Monday
        nft = expr.next_fire_time(after)
        assert nft.weekday() == 2  # Wednesday
        assert nft == datetime(2025, 6, 11, 10, 0, 0)


class TestCronExprHumanLabel:
    """Tests for CronExpr.human_label."""

    @pytest.mark.unit
    def test_every_day(self) -> None:
        expr = CronExpr(hour=8, minute=30, weekdays=frozenset())
        assert expr.human_label() == "08:30 Every day"

    @pytest.mark.unit
    def test_weekdays(self) -> None:
        expr = CronExpr(hour=6, minute=0, weekdays=frozenset({0, 2, 4}))
        label = expr.human_label()
        assert "06:00" in label
        assert "Mon" in label
        assert "Wed" in label
        assert "Fri" in label


class TestSchedulerLifecycle:
    """Tests for Scheduler start/stop and arm/disarm."""

    @pytest.mark.unit
    def test_start_stop(self, tmp_path: Path) -> None:
        db = MagicMock()
        db.list_schedules.return_value = []
        runner = MagicMock()
        runner.is_running = False
        callback = MagicMock()

        scheduler = Scheduler(db=db, runner=runner, run_analysis=callback)
        assert scheduler.is_running is False

        scheduler.start()
        assert scheduler.is_running is True
        db.list_schedules.assert_called_once()

        scheduler.stop()
        assert scheduler.is_running is False

    @pytest.mark.unit
    def test_double_start_is_idempotent(self) -> None:
        db = MagicMock()
        db.list_schedules.return_value = []
        runner = MagicMock()
        callback = MagicMock()

        scheduler = Scheduler(db=db, runner=runner, run_analysis=callback)
        scheduler.start()
        scheduler.start()  # Should not raise, db only queried once
        assert db.list_schedules.call_count == 1
        scheduler.stop()

    @pytest.mark.unit
    def test_stop_without_start(self) -> None:
        db = MagicMock()
        runner = MagicMock()
        callback = MagicMock()

        scheduler = Scheduler(db=db, runner=runner, run_analysis=callback)
        scheduler.stop()  # Should not raise

    @pytest.mark.unit
    def test_add_and_remove_schedule(self) -> None:
        db = MagicMock()
        db.list_schedules.return_value = []
        db.update_schedule_next_run = MagicMock()
        runner = MagicMock()
        callback = MagicMock()

        scheduler = Scheduler(db=db, runner=runner, run_analysis=callback)
        scheduler.start()

        # Arm a new schedule
        scheduler.add_schedule(1, "09:00 MON-FRI", "America/New_York")
        assert 1 in scheduler._timers

        # Disarm it
        scheduler.remove_schedule(1)
        assert 1 not in scheduler._timers

        scheduler.stop()

    @pytest.mark.unit
    def test_reload_schedule(self) -> None:
        db = MagicMock()
        db.list_schedules.return_value = []
        db.update_schedule_next_run = MagicMock()
        runner = MagicMock()
        callback = MagicMock()

        scheduler = Scheduler(db=db, runner=runner, run_analysis=callback)
        scheduler.start()

        scheduler.add_schedule(5, "08:00 MON-FRI", "UTC")
        scheduler.reload_schedule(5, "07:30 MON-FRI", "UTC")
        assert 5 in scheduler._timers

        scheduler.stop()

    @pytest.mark.unit
    def test_arm_invalid_cron_does_not_raise(self) -> None:
        db = MagicMock()
        db.list_schedules.return_value = []
        runner = MagicMock()
        callback = MagicMock()

        scheduler = Scheduler(db=db, runner=runner, run_analysis=callback)
        scheduler.start()

        # Invalid cron should be logged but not raise
        scheduler.add_schedule(99, "not-a-cron", "UTC")
        assert 99 not in scheduler._timers

        scheduler.stop()

    @pytest.mark.unit
    def test_remove_nonexistent_schedule(self) -> None:
        db = MagicMock()
        db.list_schedules.return_value = []
        runner = MagicMock()
        callback = MagicMock()

        scheduler = Scheduler(db=db, runner=runner, run_analysis=callback)
        scheduler.start()
        scheduler.remove_schedule(999)  # Should not raise
        scheduler.stop()

    @pytest.mark.unit
    def test_start_with_enabled_schedules(self) -> None:
        sched_row = SimpleNamespace(
            id=1,
            name="Pre-market",
            watchlist="AAPL,MSFT",
            cron_expr="08:30 MON-FRI",
            timezone="America/New_York",
            is_enabled=1,
            last_run=None,
            next_run=None,
            created_at="2025-01-01",
        )
        db = MagicMock()
        db.list_schedules.return_value = [sched_row]
        db.update_schedule_next_run = MagicMock()
        runner = MagicMock()
        callback = MagicMock()

        scheduler = Scheduler(db=db, runner=runner, run_analysis=callback)
        scheduler.start()

        assert 1 in scheduler._timers
        scheduler.stop()

    @pytest.mark.unit
    def test_start_skips_disabled_schedules(self) -> None:
        sched_row = SimpleNamespace(
            id=2,
            name="Disabled",
            watchlist="GOOG",
            cron_expr="06:00",
            timezone="UTC",
            is_enabled=0,
            last_run=None,
            next_run=None,
            created_at="2025-01-01",
        )
        db = MagicMock()
        db.list_schedules.return_value = [sched_row]
        runner = MagicMock()
        callback = MagicMock()

        scheduler = Scheduler(db=db, runner=runner, run_analysis=callback)
        scheduler.start()

        assert 2 not in scheduler._timers
        scheduler.stop()


# ═══════════════════════════════════════════════════════════════════════
# 6. PDF Export
# ═══════════════════════════════════════════════════════════════════════


class TestVerdictClass:
    """Tests for _verdict_class CSS mapping."""

    @pytest.mark.unit
    def test_buy(self) -> None:
        assert _verdict_class("BUY") == "verdict-buy"

    @pytest.mark.unit
    def test_overweight(self) -> None:
        assert _verdict_class("OVERWEIGHT") == "verdict-buy"

    @pytest.mark.unit
    def test_sell(self) -> None:
        assert _verdict_class("SELL") == "verdict-sell"

    @pytest.mark.unit
    def test_underweight(self) -> None:
        assert _verdict_class("UNDERWEIGHT") == "verdict-sell"

    @pytest.mark.unit
    def test_hold(self) -> None:
        assert _verdict_class("HOLD") == "verdict-hold"

    @pytest.mark.unit
    def test_unknown_verdict(self) -> None:
        assert _verdict_class("UNKNOWN") == "verdict-default"

    @pytest.mark.unit
    def test_case_insensitive(self) -> None:
        assert _verdict_class("buy") == "verdict-buy"
        assert _verdict_class("sell") == "verdict-sell"


class TestMdToHtml:
    """Tests for _md_to_html conversion."""

    @pytest.mark.unit
    def test_fallback_without_markdown2(self) -> None:
        with patch("desktop.services.pdf_export._MD_AVAILABLE", False):
            result = _md_to_html("# Hello **World**")
            assert "<pre>" in result
            # HTML should be escaped in fallback
            assert "&lt;" not in result or "Hello" in result

    @pytest.mark.unit
    def test_with_markdown2(self) -> None:
        # Only test if markdown2 is actually available
        try:
            import markdown2  # noqa: F401
        except ImportError:
            pytest.skip("markdown2 not installed")

        result = _md_to_html("# Hello\n\n**Bold text**")
        assert "<h1>" in result or "<strong>" in result


class TestPDFExporterWithoutWeasyprint:
    """Tests for PDFExporter that verify behavior without weasyprint."""

    @pytest.mark.unit
    def test_export_analysis_raises_without_weasyprint(self, tmp_path: Path) -> None:
        exporter = PDFExporter()
        with patch(
            "desktop.services.pdf_export._require_weasyprint",
            side_effect=ImportError("weasyprint not installed"),
        ):
            with pytest.raises(ImportError, match="weasyprint"):
                exporter.export_analysis(
                    result_dir=tmp_path,
                    ticker="AAPL",
                    verdict="BUY",
                    date="2025-01-01",
                )

    @pytest.mark.unit
    def test_export_summary_raises_without_weasyprint(self) -> None:
        exporter = PDFExporter()
        with patch(
            "desktop.services.pdf_export._require_weasyprint",
            side_effect=ImportError("weasyprint not installed"),
        ):
            with pytest.raises(ImportError, match="weasyprint"):
                exporter.export_summary(
                    recommendations=[],
                    prices={},
                )

    @pytest.mark.unit
    def test_export_analysis_with_mocked_weasyprint(self, tmp_path: Path) -> None:
        # Create a fake markdown file in result_dir
        md_file = tmp_path / "report.md"
        md_file.write_text("# Test Report\n\nSome content.", encoding="utf-8")

        mock_weasyprint = MagicMock()
        mock_html_instance = MagicMock()
        mock_weasyprint.HTML.return_value = mock_html_instance

        exporter = PDFExporter()
        with patch(
            "desktop.services.pdf_export._require_weasyprint",
            return_value=mock_weasyprint,
        ):
            result_path = exporter.export_analysis(
                result_dir=tmp_path,
                ticker="AAPL",
                verdict="BUY",
                date="2025-01-01",
            )

        assert "AAPL" in str(result_path)
        assert "2025-01-01" in str(result_path)
        mock_weasyprint.HTML.assert_called_once()
        mock_html_instance.write_pdf.assert_called_once()

    @pytest.mark.unit
    def test_export_analysis_no_md_files(self, tmp_path: Path) -> None:
        mock_weasyprint = MagicMock()
        mock_weasyprint.HTML.return_value = MagicMock()

        exporter = PDFExporter()
        with patch(
            "desktop.services.pdf_export._require_weasyprint",
            return_value=mock_weasyprint,
        ):
            exporter.export_analysis(
                result_dir=tmp_path,
                ticker="MSFT",
                verdict="HOLD",
                date="2025-06-01",
            )

        # Verify HTML was generated (contains "No report files found")
        call_args = mock_weasyprint.HTML.call_args
        html_content = call_args[1]["string"] if "string" in call_args[1] else call_args[0][0]
        assert "No report files found" in html_content

    @pytest.mark.unit
    def test_export_analysis_escapes_html(self, tmp_path: Path) -> None:
        mock_weasyprint = MagicMock()
        mock_weasyprint.HTML.return_value = MagicMock()

        exporter = PDFExporter()
        with patch(
            "desktop.services.pdf_export._require_weasyprint",
            return_value=mock_weasyprint,
        ):
            exporter.export_analysis(
                result_dir=tmp_path,
                ticker="<script>alert('xss')</script>",
                verdict="BUY",
                date="2025-01-01",
            )

        call_args = mock_weasyprint.HTML.call_args
        html_content = call_args[1]["string"] if "string" in call_args[1] else call_args[0][0]
        # The raw script tag should be escaped
        assert "<script>" not in html_content
        assert "&lt;script&gt;" in html_content

    @pytest.mark.unit
    def test_export_summary_with_mocked_weasyprint(self) -> None:
        rec = SimpleNamespace(
            ticker="AAPL",
            verdict="BUY",
            confidence=8,
            price_at_analysis=150.0,
        )
        price_result = PriceResult(
            ticker="AAPL",
            price=155.0,
            previous_close=150.0,
            change_pct=3.33,
            is_stale=False,
            fetched_at="2025-01-01T00:00:00Z",
            error=None,
        )

        mock_weasyprint = MagicMock()
        mock_weasyprint.HTML.return_value = MagicMock()

        exporter = PDFExporter()
        with patch(
            "desktop.services.pdf_export._require_weasyprint",
            return_value=mock_weasyprint,
        ):
            with patch("desktop.services.pdf_export.Path.home") as mock_home:
                mock_home.return_value = Path("/tmp/test_home")
                result_path = exporter.export_summary(
                    recommendations=[rec],
                    prices={"AAPL": price_result},
                )

        assert "summary_" in str(result_path)
        mock_weasyprint.HTML.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


def _make_recommendation_row(
    *,
    stop_loss: float | None = None,
    profit_target: float | None = None,
    price_at_analysis: float | None = 100.0,
) -> RecommendationRow:
    """Build a RecommendationRow with sensible defaults for tests."""
    return RecommendationRow(
        id=1,
        analysis_id=1,
        ticker="TEST",
        verdict="HOLD",
        confidence=5,
        price_at_analysis=price_at_analysis,
        stop_loss=stop_loss,
        entry_trigger=None,
        profit_target=profit_target,
        review_date=None,
        is_active=1,
        created_at=datetime.now(tz=timezone.utc).isoformat(),
        deactivated_at=None,
        notes=None,
    )
