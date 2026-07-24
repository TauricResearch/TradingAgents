"""Institutional report generation (track T1): self-contained report.html,
report.pdf, and PNG charts — opt-in, best-effort, no fabricated numbers."""

from datetime import datetime, timedelta

import pytest

matplotlib = pytest.importorskip("matplotlib")  # backtest-report extra

from tradingagents.pro.backtest.broker import ClosedTrade  # noqa: E402
from tradingagents.pro.backtest.metrics import performance_report  # noqa: E402
from tradingagents.pro.backtest.report import extended_report  # noqa: E402
from tradingagents.pro.backtest.report_html import generate_report  # noqa: E402

_T0 = datetime(2024, 1, 1)


def _trade(n: int, pnl: float) -> ClosedTrade:
    return ClosedTrade(
        symbol="BTCUSD", side="BUY", quantity=1.0,
        entry_price=100.0, exit_price=100.0 + pnl,
        opened_at=_T0 + timedelta(days=n),
        closed_at=_T0 + timedelta(days=n + 1),
        pnl=pnl, reason="take_profit" if pnl >= 0 else "stop",
        recommendation_id=f"rec-{n}")


def _inputs():
    trades = [_trade(0, 5.0), _trade(2, -3.0), _trade(4, 8.0), _trade(6, -2.0)]
    equity = [100_000.0, 100_500.0, 100_200.0, 101_000.0, 100_800.0, 101_500.0]
    timestamps = [_T0 + timedelta(days=i) for i in range(len(equity))]
    closes = [100.0 + i for i in range(len(equity))]
    report = performance_report(equity, trades, periods_per_year=365).as_dict()
    ext = extended_report(equity, trades, timestamps, closes, 100_000.0,
                          years=len(equity) / 365.25, periods_per_year=365)
    from dataclasses import asdict
    return trades, equity, timestamps, closes, report, asdict(ext)


def test_generate_report_writes_self_contained_html_and_pdf(tmp_path):
    trades, equity, timestamps, closes, report, ext = _inputs()
    files = generate_report(
        tmp_path, meta={"title": "BTCUSD · demo", "symbol": "BTCUSD",
                        "timeframe": "1d", "duration": "7D"},
        report=report, extended=ext, equity_curve=equity, timestamps=timestamps,
        benchmark_closes=closes, initial_equity=100_000.0, trades=trades,
        states_by_rec_id={})  # deterministic run → no debate state

    assert "report.html" in files and "report.pdf" in files
    assert any(f.startswith("charts/") for f in files)

    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    # self-contained: charts inlined as base64, no external file references
    assert "data:image/png;base64," in html
    assert "Total return" in html and "CAGR" in html  # perf + extended rows
    assert "src='charts/" not in html and 'src="charts/' not in html

    pdf = (tmp_path / "report.pdf").read_bytes()
    assert pdf[:5] == b"%PDF-"
    assert (tmp_path / "charts" / "equity.png").is_file()


def test_generate_report_without_extended_still_renders(tmp_path):
    # extended bundle absent (e.g. pandas unavailable at run time) — the report
    # still renders from the base performance metrics, no crash.
    trades, equity, timestamps, closes, report, _ = _inputs()
    files = generate_report(
        tmp_path, meta={"title": "no-ext"}, report=report, extended=None,
        equity_curve=equity, timestamps=timestamps, benchmark_closes=closes,
        initial_equity=100_000.0, trades=trades, states_by_rec_id={})
    assert "report.html" in files
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "Total return" in html and "CAGR" not in html  # no extended rows
