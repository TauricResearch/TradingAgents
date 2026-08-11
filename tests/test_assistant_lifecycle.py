"""Integration tests for the three mechanisms that only fire days apart.

A rule exit, a rotation demotion and a screener expiry each need real elapsed
time in production — a stop takes weeks to be hit, a demotion needs five Holds,
an expiry needs 21 quiet days. So they were the parts of the system that had
never actually run: the *pure* logic was covered (signal series, rotation
arithmetic) while the wiring that turns a decision into a database row was not.
That is the wrong half to leave untested. A rule that says "exit" and an engine
that books nothing looks identical to a rule that says "hold".

These drive each path against a real (temporary) database and assert the row
that should exist afterwards, so a 15-day wait is not the only evidence.
"""

import asyncio
from datetime import datetime, timedelta

import pandas as pd
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.entities import PaperAccount, Position, Trade, WatchlistTicker


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    """A throwaway SQLite database wired in place of the real one.

    The assertion is not paranoia: these tests delete watchlist rows and sell
    positions, and the live database holds a running paper-trading experiment.
    Pointing at it by accident would be unrecoverable, so the fixture refuses to
    run unless the URL is under tmp_path.
    """
    import app.models.base as base

    url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    assert str(tmp_path) in url and "assistant.db" not in url

    engine = create_async_engine(url)
    monkeypatch.setattr(base, "_engine", engine)
    monkeypatch.setattr(base, "_session_factory", async_sessionmaker(
        engine, expire_on_commit=False
    ))
    asyncio.run(base.init_db())
    yield base.session_factory()
    asyncio.run(engine.dispose())


def _seed(factory, *rows, cash=5_000.0, book_label="tactical_donchian"):
    async def go():
        async with factory() as session, session.begin():
            session.add(PaperAccount(
                label=book_label, starting_cash=10_000.0, cash=cash
            ))
            for row in rows:
                session.add(row)
    asyncio.run(go())


def _rows(factory, model):
    async def go():
        from sqlalchemy import select
        async with factory() as session:
            return list((await session.execute(select(model))).scalars())
    return asyncio.run(go())


class TestRuleExitBooksASell:
    """The donchian arm's exit had never fired: 13 closes, all core rotations."""

    @staticmethod
    def _downtrend(rows=400):
        """Prices that fall steadily, so a 20-day-low exit triggers on the last bar."""
        close = [200.0 - i * 0.25 for i in range(rows)]
        idx = pd.date_range("2024-01-01", periods=rows, freq="D")
        return pd.DataFrame(
            {"Open": close, "High": [c * 1.001 for c in close],
             "Low": [c * 0.999 for c in close], "Close": close,
             "Volume": [1_000_000] * rows},
            index=idx,
        )

    def test_donchian_exit_signal_becomes_a_recorded_sell(self, temp_db, monkeypatch):
        import app.services.tactical.engine as eng

        held = Position(
            account_type="tac_donchian", symbol="AMZN", quantity=10.0,
            avg_price=100.0, currency="USD", market="us",
            note="rule donchian_breakout",
        )
        _seed(temp_db, held)

        async def fake_universe(book="tactical"):
            return [("AMZN", "us", "satellite")]

        async def no_telegram(self, text):
            return None

        monkeypatch.setattr(eng, "_universe", fake_universe)
        monkeypatch.setattr(eng, "_history_sync", lambda symbol: self._downtrend())
        # Notifier is imported inside run_tactical, so patch it at its source.
        monkeypatch.setattr("app.services.notifier.Notifier.send_telegram", no_telegram)
        # 120 vs a 100 entry: a winning exit, so the win rate has something to
        # count and cannot pass by defaulting everything to a loss.
        monkeypatch.setattr("app.services.paper_broker.live_price",
                            lambda symbol: _async(120.0))

        actions = asyncio.run(eng.run_tactical(book="tactical_donchian"))

        assert actions, "the rule said exit and the engine booked nothing"
        assert _rows(temp_db, Position) == [], "position was not closed"

        trades = _rows(temp_db, Trade)
        assert len(trades) == 1
        sell = trades[0]
        assert sell.side == "sell"
        assert sell.symbol == "AMZN"
        assert sell.account_type == "tac_donchian"
        assert "exit" in sell.reason
        # 10 * (120 - 100) = 200 gross, less the 5bps US-large exit cost on
        # $1,200 of proceeds. Asserted net rather than gross: a backtest that
        # forgets costs is how a losing rule looks profitable.
        assert sell.realized_pnl_usd == pytest.approx(200.0 - 1200 * 0.0005)
        assert sell.realized_pnl_usd < 200.0, "exit booked no transaction cost"

    def test_the_exit_counts_as_a_strategy_trade_not_a_core_rotation(self):
        """The whole point of the fix: this must reach the win rate."""
        from app.services.core_holding import is_core_trade

        assert is_core_trade("tactical donchian_breakout exit") is False
        assert is_core_trade("core sold to fund signal") is True
        assert is_core_trade("core sweep") is True
        # The defensive exit used to be the one core trade that hid itself.
        assert is_core_trade("core exit: SPY below 200d average") is True

    def test_rule_still_long_does_not_sell(self, temp_db, monkeypatch):
        """Guards the inverse: an uptrend must leave the position alone."""
        import app.services.tactical.engine as eng

        rows = 400
        close = [100.0 + i * 0.25 for i in range(rows)]
        up = pd.DataFrame(
            {"Open": close, "High": [c * 1.001 for c in close],
             "Low": [c * 0.999 for c in close], "Close": close,
             "Volume": [1_000_000] * rows},
            index=pd.date_range("2024-01-01", periods=rows, freq="D"),
        )
        _seed(temp_db, Position(
            account_type="tac_donchian", symbol="AMZN", quantity=10.0,
            avg_price=100.0, currency="USD", market="us", note="rule donchian_breakout",
        ))

        async def fake_universe(book="tactical"):
            return [("AMZN", "us", "satellite")]

        monkeypatch.setattr(eng, "_universe", fake_universe)
        monkeypatch.setattr(eng, "_history_sync", lambda symbol: up)
        monkeypatch.setattr("app.services.notifier.Notifier.send_telegram",
                            lambda self, text: _async(None))
        monkeypatch.setattr("app.services.paper_broker.live_price",
                            lambda symbol: _async(120.0))

        asyncio.run(eng.run_tactical(book="tactical_donchian"))
        assert len(_rows(temp_db, Position)) == 1
        assert [t for t in _rows(temp_db, Trade) if t.side == "sell"] == []


class TestRotationPersists:
    """next_rotation_state is well tested; that anything SAVES its answer was not."""

    @staticmethod
    def _outcome(rating):
        from app.services.runner import AnalysisOutcome

        return AnalysisOutcome(
            symbol="TEST", trade_date="2026-08-11", rating=rating,
            decision_text="Review in 7 days.", report_path=None, duration_seconds=1.0,
        )

    def _persist(self, rating):
        from app.domain import Market
        from app.services.pipeline import _persist_outcome

        asyncio.run(_persist_outcome(Market.US, "TEST", None, self._outcome(rating)))

    def test_fifth_hold_demotes_daily_to_weekly(self, temp_db, monkeypatch):
        monkeypatch.setenv("ASSISTANT_DEMOTE_AFTER_HOLDS", "5")
        from app.core.config import get_settings

        get_settings.cache_clear()
        _seed(temp_db, WatchlistTicker(
            symbol="TEST", market="us", tier="daily", added_by="manual",
            category="core", consecutive_holds=4,
        ))

        self._persist("Hold")

        ticker = _rows(temp_db, WatchlistTicker)[0]
        assert ticker.consecutive_holds == 5
        assert ticker.tier == "weekly", "the 5th Hold did not demote"
        assert ticker.last_rating == "Hold"
        assert ticker.last_run_at is not None
        get_settings.cache_clear()

    def test_fourth_hold_does_not_demote_yet(self, temp_db):
        _seed(temp_db, WatchlistTicker(
            symbol="TEST", market="us", tier="daily", added_by="manual",
            category="core", consecutive_holds=3,
        ))
        self._persist("Hold")
        ticker = _rows(temp_db, WatchlistTicker)[0]
        assert ticker.consecutive_holds == 4
        assert ticker.tier == "daily"

    def test_actionable_rating_resets_the_boredom_counter(self, temp_db):
        """A demoted ticker earns attention back through review dates, not tier."""
        _seed(temp_db, WatchlistTicker(
            symbol="TEST", market="us", tier="weekly", added_by="manual",
            category="core", consecutive_holds=9,
        ))
        self._persist("Overweight")
        ticker = _rows(temp_db, WatchlistTicker)[0]
        assert ticker.consecutive_holds == 0, "an actionable call did not reset holds"
        assert ticker.last_rating == "Overweight"

    def test_screener_pick_fast_demotes_on_one_hold(self, temp_db):
        _seed(temp_db, WatchlistTicker(
            symbol="TEST", market="us", tier="daily", added_by="screener",
            category="satellite", consecutive_holds=0,
        ))
        self._persist("Hold")
        assert _rows(temp_db, WatchlistTicker)[0].tier == "weekly"


class TestScreenerExpiry:
    """Untested entirely, and it is the only path that DELETES watchlist rows."""

    @staticmethod
    def _stale(**kw):
        defaults = {
            "symbol": "STALE", "market": "us", "tier": "weekly",
            "added_by": "screener", "category": "satellite", "last_rating": "Hold",
            "last_run_at": datetime.utcnow() - timedelta(days=60),
        }
        return WatchlistTicker(**{**defaults, **kw})

    def _expire(self):
        from app.services.screener import expire_stale_picks

        return asyncio.run(expire_stale_picks())

    def test_stale_boring_screener_pick_is_removed(self, temp_db):
        _seed(temp_db, self._stale())
        assert self._expire() == ["STALE"]
        assert _rows(temp_db, WatchlistTicker) == []

    def test_open_position_pins_a_ticker_forever(self, temp_db):
        """The hard rule: something you own is never expired out from under you."""
        _seed(temp_db, self._stale(), Position(
            account_type="paper", symbol="STALE", quantity=5.0,
            avg_price=10.0, currency="USD", market="us",
        ))
        assert self._expire() == []
        assert len(_rows(temp_db, WatchlistTicker)) == 1

    @pytest.mark.parametrize("field,value", [
        ("added_by", "manual"),      # hand-picked, not the screener's to remove
        ("category", "core"),        # permanent holding
        ("last_rating", "Buy"),      # still interesting
    ])
    def test_only_boring_screener_satellites_expire(self, temp_db, field, value):
        _seed(temp_db, self._stale(**{field: value}))
        assert self._expire() == []
        assert len(_rows(temp_db, WatchlistTicker)) == 1

    def test_a_pick_with_no_verdict_after_the_window_also_expires(self, temp_db):
        """last_rating=None counts as boring, deliberately.

        It means the pick was run but produced no rating (an errored analysis).
        Three weeks of that is not a candidate worth a seat, and the screener can
        rediscover it. Asserted explicitly because it reads like an oversight.
        """
        _seed(temp_db, self._stale(last_rating=None))
        assert self._expire() == ["STALE"]

    def test_recent_pick_survives_the_window(self, temp_db, monkeypatch):
        monkeypatch.setenv("SCREENER_EXPIRY_DAYS", "21")
        from app.core.config import get_settings

        get_settings.cache_clear()
        _seed(temp_db, self._stale(last_run_at=datetime.utcnow() - timedelta(days=5)))
        assert self._expire() == []
        get_settings.cache_clear()


class TestWinRateExcludesCoreRotations:
    """tactical_donchian read "4/13 won" having never once exited a position.

    All 13 closes were core sweeps — the index core being sold to free cash for
    a signal. Folding those into the win rate does not dilute the number, it
    replaces it: the arm's actual record was 0 exits.
    """

    def _summary(self, factory, monkeypatch, trades):
        import app.api.portfolio as api

        async def go():
            async with factory() as session, session.begin():
                session.add(PaperAccount(
                    label="tactical_donchian", starting_cash=10_000.0, cash=10_000.0
                ))
                for t in trades:
                    session.add(t)
        asyncio.run(go())

        monkeypatch.setattr(api, "_batch_prices_sync", lambda symbols: {})

        async def no_bench(created):
            return 0.0

        monkeypatch.setattr(api, "_benchmark_return_pct", no_bench)
        monkeypatch.setattr("app.services.core_holding.core_trend_ok",
                            lambda book="strategic": _async(True))

        async def call():
            async with factory() as session, session.begin():
                response = await api.portfolio(session)
            return next(b for b in response.books if b.label == "tactical_donchian")

        return asyncio.run(call())

    @staticmethod
    def _sell(reason, pnl):
        return Trade(
            account_type="tac_donchian", symbol="IVV", side="sell", quantity=1.0,
            price=100.0, currency="USD", reason=reason, realized_pnl_usd=pnl,
        )

    def test_core_rotations_are_not_counted_as_exits(self, temp_db, monkeypatch):
        book = self._summary(temp_db, monkeypatch, [
            self._sell("core sold to fund signal", -0.10) for _ in range(13)
        ])
        assert book.closed_trades == 0, "core sweeps still counted as exits"
        assert book.winning_trades == 0
        assert book.core_rotations == 13
        # The money is still reported — it is real, just not a strategy result.
        assert book.realised_pnl_usd == pytest.approx(-1.30)
        assert book.core_realised_pnl_usd == pytest.approx(-1.30)

    def test_real_exits_are_counted_and_core_is_kept_separate(self, temp_db, monkeypatch):
        book = self._summary(temp_db, monkeypatch, [
            *[self._sell("core sold to fund signal", -0.10) for _ in range(13)],
            self._sell("tactical donchian_breakout exit", 200.0),
            self._sell("stop-loss 90.00 hit", -50.0),
        ])
        assert book.closed_trades == 2, "strategy exits miscounted"
        assert book.winning_trades == 1          # 1 of 2, not 5 of 15
        assert book.core_rotations == 13
        assert book.realised_pnl_usd == pytest.approx(200.0 - 50.0 - 1.30)
        assert book.core_realised_pnl_usd == pytest.approx(-1.30)

    def test_defensive_core_exit_is_also_excluded(self, temp_db, monkeypatch):
        """The reason string that used to identify itself as a strategy exit."""
        book = self._summary(temp_db, monkeypatch, [
            self._sell("core exit: SPY below 200d average", -12.0),
        ])
        assert book.closed_trades == 0
        assert book.core_rotations == 1


def _async(value):
    """Wrap a plain value as an awaitable, for monkeypatching async functions."""
    async def coro():
        return value
    return coro()
