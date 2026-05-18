from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime

import pandas as pd
import pytz
import yfinance as yf

from .aggregator import aggregate, audit_positions, detect_condition
from .broker import load_portfolio
from .config import Aggressiveness, config
from .runner import run_tickers
from .scheduler import build_scheduler
from .screener import get_market_regime, screen_candidates
from .web import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
ET = pytz.timezone("America/New_York")

os.makedirs(config.data_dir, exist_ok=True)


# ── State helpers ────────────────────────────────────────────────────────────

def _patch_state(patch: dict) -> None:
    state: dict = {}
    if os.path.exists(config.state_file):
        try:
            with open(config.state_file, encoding="utf-8") as fh:
                state = json.load(fh)
        except (json.JSONDecodeError, OSError):
            pass
    state.update(patch)
    with open(config.state_file, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, default=str)


def _set_stage(stage: str, progress: int, detail: str = "") -> None:
    """Patch just the progress fields — cheap, called frequently during runs."""
    _patch_state({"stage": stage, "progress": progress, "stage_detail": detail})


# ── Serializers ──────────────────────────────────────────────────────────────

def _serialize_actions(actions) -> list:
    return [
        {
            "ticker": a.ticker,
            "action": a.action,
            "signal": a.signal,
            "score": a.score,
            "rationale": a.rationale,
            "owned": a.owned,
            "price": a.price,
            "affordable": a.affordable,
        }
        for a in actions
    ]


def _fetch_prices(tickers: list, portfolio) -> dict:
    """Batch-fetch current prices. Uses owned position prices where available."""
    price_map: dict[str, float] = {p.ticker: p.current_price for p in portfolio.positions}
    new_tickers = [t for t in tickers if t not in price_map]
    if not new_tickers:
        return price_map
    try:
        data = yf.download(new_tickers, period="2d", auto_adjust=True, progress=False, threads=True)
        if not data.empty:
            close = (
                data["Close"]
                if isinstance(data.columns, pd.MultiIndex)
                else data[["Close"]].rename(columns={"Close": new_tickers[0]})
            )
            for t in new_tickers:
                if t in close.columns:
                    s = close[t].dropna()
                    if not s.empty:
                        price_map[t] = float(s.iloc[-1])
    except Exception as exc:
        logger.warning("Price fetch failed: %s", exc)
    return price_map


# ── Run functions ────────────────────────────────────────────────────────────

def run_intraday() -> None:
    """Check owned positions for sell signals (runs 4x per trading day)."""
    logger.info("--- Intraday check ---")
    _set_stage("Loading portfolio", 2)

    trade_date = date.today()
    portfolio = load_portfolio(config.data_dir)
    owned_tickers = [p.ticker for p in portfolio.positions]

    if not owned_tickers:
        logger.info("No owned positions to check")
        _patch_state({"running": False, "stage": "No positions to check", "progress": 100, "stage_detail": ""})
        return

    _set_stage("Checking market regime", 8)
    regime = get_market_regime()

    _set_stage("Running analysis", 15, f"0/{len(owned_tickers)} positions")

    def _analysis_progress(fraction, detail):
        _set_stage("Running analysis", int(15 + fraction * 75), detail)

    results = run_tickers(owned_tickers, trade_date, config, on_progress=_analysis_progress)

    _set_stage("Aggregating results", 92)
    owned_set = {p.ticker for p in portfolio.positions}
    price_map = _fetch_prices(owned_tickers, portfolio)
    actions = aggregate(
        results, owned_set, config, trade_date,
        cash=portfolio.cash, price_map=price_map,
    )
    condition = detect_condition(portfolio.cash, portfolio.positions, config.cash_threshold)

    _patch_state({
        "last_intraday_run": datetime.now(ET).isoformat(),
        "portfolio_source": portfolio.source,
        "portfolio_positions": audit_positions(portfolio.positions),
        "cash": portfolio.cash,
        "actions": _serialize_actions(actions),
        "aggressiveness": config.aggressiveness.value,
        "condition": condition,
        "market_regime": regime,
        "running": False,
        "stage": "Complete",
        "progress": 100,
        "stage_detail": f"{len(owned_tickers)} positions reviewed",
    })
    logger.info("Intraday check complete: %d positions reviewed", len(owned_tickers))


def run_eod() -> None:
    """Screen NASDAQ candidates and run full analysis (EOD + Monday pre-market)."""
    logger.info("--- EOD/pre-market scan ---")
    _set_stage("Loading portfolio", 2)

    trade_date = date.today()
    portfolio = load_portfolio(config.data_dir)

    _set_stage("Checking market regime", 5)
    regime = get_market_regime()
    logger.info("Market regime: %s", regime.get("regime"))

    # Aggressive strategy: no new long positions when market is in a downtrend
    skip_new_buys = (
        config.aggressiveness == Aggressiveness.AGGRESSIVE
        and regime.get("regime") in ("bear", "confirmed_bear")
    )

    if skip_new_buys:
        logger.info(
            "Aggressive mode: market regime is %s — skipping new buy candidates",
            regime.get("regime"),
        )
        candidates = []
        _set_stage("Screening skipped", 50, f"Regime: {regime.get('regime')} — no new longs")
    else:
        _set_stage("Screening NASDAQ candidates", 10, "Fetching ticker list…")

        def _screen_progress(fraction, detail):
            _set_stage("Screening NASDAQ candidates", int(10 + fraction * 40), detail)

        candidates = screen_candidates(
            portfolio, config, cash=portfolio.cash, on_progress=_screen_progress,
        )

    logger.info("%d candidates after screening", len(candidates))

    # Always include owned positions so sell signals are evaluated
    owned_set = {p.ticker for p in portfolio.positions}
    all_tickers = list(owned_set | set(candidates))

    _set_stage("Running analysis", 52, f"0/{len(all_tickers)} tickers")

    def _analysis_progress(fraction, detail):
        _set_stage("Running analysis", int(52 + fraction * 43), detail)

    results = run_tickers(all_tickers, trade_date, config, on_progress=_analysis_progress)

    _set_stage("Aggregating results", 97)
    price_map = _fetch_prices(all_tickers, portfolio)
    actions = aggregate(
        results, owned_set, config, trade_date,
        cash=portfolio.cash, price_map=price_map,
    )
    condition = detect_condition(portfolio.cash, portfolio.positions, config.cash_threshold)

    _patch_state({
        "last_eod_run": datetime.now(ET).isoformat(),
        "portfolio_source": portfolio.source,
        "portfolio_positions": audit_positions(portfolio.positions),
        "cash": portfolio.cash,
        "actions": _serialize_actions(actions),
        "aggressiveness": config.aggressiveness.value,
        "condition": condition,
        "market_regime": regime,
        "running": False,
        "stage": "Complete",
        "progress": 100,
        "stage_detail": f"{len(all_tickers)} tickers analyzed",
    })
    logger.info("EOD scan complete: %d tickers analyzed", len(all_tickers))


# ── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    logger.info("Starting Portfolio Advisor")

    scheduler = build_scheduler(config, run_intraday, run_eod)
    scheduler.start()
    logger.info(
        "Scheduler started: %d jobs registered",
        len(scheduler.get_jobs()),
    )

    app = create_app(config, run_eod)
    logger.info("Web UI at http://%s:%d", config.web_host, config.web_port)
    app.run(host=config.web_host, port=config.web_port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
