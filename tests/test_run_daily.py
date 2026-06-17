"""Tests for the headless scheduled-runner driver."""

from __future__ import annotations

import datetime as _dt
import logging

import pytest


@pytest.mark.unit
class TestLoadWatchlist:
    def test_loads_yaml(self, tmp_path, monkeypatch):
        f = tmp_path / "watchlist.yaml"
        f.write_text(
            "tickers:\n"
            "  - symbol: BTC-USD\n"
            "    asset_type: crypto\n"
            "  - symbol: NVDA\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("TRADINGAGENTS_WATCHLIST_PATH", str(f))
        from tradingagents.watchlist import load_watchlist

        entries = load_watchlist()
        assert [e.symbol for e in entries] == ["BTC-USD", "NVDA"]
        assert entries[0].asset_type == "crypto"
        assert entries[1].asset_type == "stock"  # default

    def test_missing_file_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRADINGAGENTS_WATCHLIST_PATH", str(tmp_path / "absent.yaml"))
        from tradingagents.watchlist import load_watchlist

        assert load_watchlist() == []

    def test_invalid_asset_type_raises(self, tmp_path, monkeypatch):
        f = tmp_path / "watchlist.yaml"
        f.write_text(
            "tickers:\n  - symbol: BTC-USD\n    asset_type: forex\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("TRADINGAGENTS_WATCHLIST_PATH", str(f))
        from tradingagents.watchlist import load_watchlist

        with pytest.raises(ValueError, match="asset_type"):
            load_watchlist()

    def test_missing_symbol_raises(self, tmp_path, monkeypatch):
        f = tmp_path / "watchlist.yaml"
        f.write_text("tickers:\n  - asset_type: stock\n", encoding="utf-8")
        monkeypatch.setenv("TRADINGAGENTS_WATCHLIST_PATH", str(f))
        from tradingagents.watchlist import load_watchlist

        with pytest.raises(ValueError, match="symbol"):
            load_watchlist()

    def test_analysts_override_preserved(self, tmp_path, monkeypatch):
        f = tmp_path / "watchlist.yaml"
        f.write_text(
            "tickers:\n"
            "  - symbol: NVDA\n"
            "    analysts: [market, news]\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("TRADINGAGENTS_WATCHLIST_PATH", str(f))
        from tradingagents.watchlist import load_watchlist

        entries = load_watchlist()
        assert entries[0].analysts == ["market", "news"]


def _mock_final_state(decision_text: str) -> dict:
    """Build a final_state shape that save_report_to_disk can write."""
    return {
        "market_report": "Market analysis text.",
        "sentiment_report": "Sentiment analysis text.",
        "news_report": "News analysis text.",
        "fundamentals_report": "Fundamentals analysis text.",
        "investment_debate_state": {
            "bull_history": "Bull case.",
            "bear_history": "Bear case.",
            "judge_decision": "Research manager decision.",
        },
        "trader_investment_plan": "Trader plan.",
        "risk_debate_state": {
            "aggressive_history": "Aggressive.",
            "conservative_history": "Conservative.",
            "neutral_history": "Neutral.",
            "judge_decision": decision_text,
        },
    }


_DECISION = (
    "**Rating**: Overweight\n\n"
    "**Executive Summary**: Buy the dip.\n\n"
    "**Investment Thesis**: Strong bullish setup.\n\n"
    "**Price Target**: 77400.0\n\n"
    "**Time Horizon**: 3-6 mesi\n"
)


class _FakeTradingAgentsGraph:
    """Drop-in replacement that skips LLM/graph wiring.

    ``propagate`` is configurable per test so we can simulate success,
    selective failure, or total failure without ever calling the real
    LangGraph pipeline.
    """

    instances: list[_FakeTradingAgentsGraph] = []

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs
        self.args = args
        self.instances.append(self)

    def propagate(self, ticker, date, asset_type="stock"):
        if self.kwargs.get("fail_for") and ticker in self.kwargs["fail_for"]:
            raise RuntimeError(f"simulated propagate failure for {ticker}")
        return _mock_final_state(_DECISION), "BUY"


@pytest.mark.unit
class TestRunDaily:
    def _install_fake_graph(self, monkeypatch):
        """Swap the real TradingAgentsGraph for the lightweight fake."""
        from tradingagents.graph import trading_graph as tg_mod

        _FakeTradingAgentsGraph.instances = []
        monkeypatch.setattr(tg_mod, "TradingAgentsGraph", _FakeTradingAgentsGraph)
        # Also re-export it from scripts.run_daily so the import in that
        # module resolves to the same patched symbol.
        from scripts import run_daily

        monkeypatch.setattr(run_daily, "TradingAgentsGraph", _FakeTradingAgentsGraph)
        return _FakeTradingAgentsGraph

    def test_run_processes_each_ticker(self, tmp_path, monkeypatch):
        watchlist = tmp_path / "watchlist.yaml"
        watchlist.write_text(
            "tickers:\n  - symbol: BTC-USD\n    asset_type: crypto\n  - symbol: NVDA\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("TRADINGAGENTS_WATCHLIST_PATH", str(watchlist))
        self._install_fake_graph(monkeypatch)

        from scripts import run_daily
        from tradingagents.notifications import telegram

        # Stub Telegram's send_report so we don't hit the network.
        sent: list[str] = []
        monkeypatch.setattr(
            telegram,
            "send_report",
            lambda *a, **kw: sent.append(a[0]) or True,
        )

        reports_root = tmp_path / "reports"
        code = run_daily.run(
            analysis_date=_dt.date.today().isoformat(),
            reports_root=reports_root,
        )
        assert code == run_daily.EXIT_OK
        assert set(sent) == {"BTC-USD", "NVDA"}
        # Two timestamped report directories should exist.
        created = sorted(p.name for p in reports_root.iterdir())
        assert any(name.startswith("BTC-USD_") for name in created)
        assert any(name.startswith("NVDA_") for name in created)

    def test_run_continues_after_one_ticker_fails(self, tmp_path, monkeypatch, caplog):
        watchlist = tmp_path / "watchlist.yaml"
        watchlist.write_text(
            "tickers:\n  - symbol: BTC-USD\n  - symbol: ETH-USD\n  - symbol: NVDA\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("TRADINGAGENTS_WATCHLIST_PATH", str(watchlist))
        self._install_fake_graph(monkeypatch)
        # Tell the fake to fail for ETH-USD
        original_init = _FakeTradingAgentsGraph.__init__

        def init_with_fail_set(self, *args, **kwargs):
            kwargs.setdefault("fail_for", {"ETH-USD"})
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(_FakeTradingAgentsGraph, "__init__", init_with_fail_set)

        from scripts import run_daily
        from tradingagents.notifications import telegram

        sent: list[str] = []
        monkeypatch.setattr(
            telegram,
            "send_report",
            lambda *a, **kw: sent.append(a[0]) or True,
        )

        with caplog.at_level(logging.ERROR):
            code = run_daily.run(
                analysis_date=_dt.date.today().isoformat(),
                reports_root=tmp_path / "reports",
            )
        assert code == run_daily.EXIT_OK
        assert set(sent) == {"BTC-USD", "NVDA"}
        # The failure was logged with enough context to diagnose
        assert any("ETH-USD" in record.message for record in caplog.records)

    def test_all_tickers_fail_returns_nonzero(self, tmp_path, monkeypatch):
        watchlist = tmp_path / "watchlist.yaml"
        watchlist.write_text(
            "tickers:\n  - symbol: A\n  - symbol: B\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("TRADINGAGENTS_WATCHLIST_PATH", str(watchlist))
        self._install_fake_graph(monkeypatch)

        from scripts import run_daily
        from tradingagents.graph import trading_graph as tg_mod
        from tradingagents.notifications import telegram

        def always_fail(self, ticker, date, asset_type="stock"):
            raise RuntimeError("nope")

        monkeypatch.setattr(tg_mod.TradingAgentsGraph, "propagate", always_fail)
        monkeypatch.setattr(telegram, "send_report", lambda *a, **kw: True)

        code = run_daily.run(
            analysis_date=_dt.date.today().isoformat(),
            reports_root=tmp_path / "reports",
        )
        assert code == run_daily.EXIT_ALL_FAILED

    def test_empty_watchlist_returns_ok(self, tmp_path, monkeypatch):
        watchlist = tmp_path / "watchlist.yaml"
        watchlist.write_text("tickers: []\n", encoding="utf-8")
        monkeypatch.setenv("TRADINGAGENTS_WATCHLIST_PATH", str(watchlist))
        self._install_fake_graph(monkeypatch)

        from scripts import run_daily

        code = run_daily.run(
            analysis_date=_dt.date.today().isoformat(),
            reports_root=tmp_path / "reports",
        )
        assert code == run_daily.EXIT_OK

    def test_missing_watchlist_returns_ok(self, tmp_path, monkeypatch):
        monkeypatch.setenv(
            "TRADINGAGENTS_WATCHLIST_PATH", str(tmp_path / "missing.yaml")
        )
        self._install_fake_graph(monkeypatch)

        from scripts import run_daily

        code = run_daily.run(
            analysis_date=_dt.date.today().isoformat(),
            reports_root=tmp_path / "reports",
        )
        assert code == run_daily.EXIT_OK

    def test_invalid_watchlist_returns_bad_exit(self, tmp_path, monkeypatch):
        watchlist = tmp_path / "watchlist.yaml"
        watchlist.write_text("tickers:\n  - asset_type: stock\n", encoding="utf-8")
        monkeypatch.setenv("TRADINGAGENTS_WATCHLIST_PATH", str(watchlist))
        self._install_fake_graph(monkeypatch)

        from scripts import run_daily

        code = run_daily.run(
            analysis_date=_dt.date.today().isoformat(),
            reports_root=tmp_path / "reports",
        )
        assert code == run_daily.EXIT_BAD_WATCHLIST

    def test_telegram_renderer_escapes_markdownv2_specials(self):
        """Telegram MarkdownV2 requires - . * _ etc. to be backslash-escaped."""
        from tradingagents.notifications import telegram
        from tradingagents.reports.exporter import DecisionSummary

        summary = DecisionSummary(
            rating="Overweight",
            price_target=77400.0,
            time_horizon="3-6 mesi",       # contains `-` and `.`
            executive_summary="Stop loss a $62.000 (1,5x ATR).",  # lots of specials
        )
        msg = telegram._render_short_message("BTC-USD", summary)
        # The deliberate template `*bold*` markers must remain, but user data
        # fields (rating, horizon, summary) must have their special chars escaped.
        assert "*BTC\\-USD*" in msg or "*" in msg  # bold rendering survives
        assert "3\\-6 mesi" in msg
        assert "62\\.000" in msg
        assert "\\(" in msg and "\\)" in msg
