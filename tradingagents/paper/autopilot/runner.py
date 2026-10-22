"""Idempotent forward orchestration: independent calendar slots, closed bars,
conditional simulated orders, research receipts, and brokerless audit.

The runner never invents missed pre-open snapshots or executes retroactively
on the assumption that information was available. It may *model* standing
stops/exits across missed sessions using real OHLC, with an explicit warning.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from tradingagents.paper.conditional import EarningsSnapshot, TradeIntent, evidence_hash
from tradingagents.paper.autopilot import feeds
from tradingagents.paper.autopilot.state import V3State, atomic_write, read
from tradingagents.paper.autopilot.decision import policy_intent, request_proposal


def _required(state: V3State) -> set[str]:
    portfolio = state.portfolio
    active = {r["plan"]["ticker"] for r in portfolio.intents.values()
              if r["status"] in ("WATCHING", "QUEUED")}
    return active | set(portfolio.book.positions) | {x["ticker"] for x in portfolio.book.orders}


def snapshot_phase(state_path: Path, *, phase: str, now: datetime | None = None,
                   fetcher=feeds.earnings_for) -> dict:
    now = now or datetime.now(timezone.utc)
    day = feeds.session_cutoff(now, phase)
    state = read(state_path)
    symbols = sorted(set(state.watchlist) | _required(state))
    home = state_path.expanduser().resolve().parent
    path = feeds.capture_earnings(home, day, phase, symbols, now, source=fetcher)
    file_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    # A later edited earnings file must not silently grant permission to buy.
    # The write follows the immutable snapshot, under the V3 CLI lock.
    state.event("EARNINGS_SNAPSHOT_CAPTURED", session=day, phase=phase,
                sha256=file_sha, verified=sum(
                    obs.verified for obs in feeds.read_earnings(home, day, phase, set(symbols), now).values()))
    atomic_write(state_path, state)
    valid = feeds.read_earnings(home, day, phase, set(symbols), now)
    return {"phase": phase, "session": day,
            "captured": len(valid), "verified": sum(v.verified is True for v in valid.values()),
            "unverified": sorted(t for t, v in valid.items() if not v.verified),
            "path": str(path), "orders_sent": 0}


def _validated_calendar(state: V3State, root: Path, session: str,
                        phase: str, active: set[str], now: datetime):
    from tradingagents.paper.conditional import EarningsSnapshot
    captured = [x for x in state.audit if x["kind"] == "EARNINGS_SNAPSHOT_CAPTURED"
                and x["details"].get("session") == session
                and x["details"].get("phase") == phase]
    file = root / "calendar" / session / (phase + ".json")
    if not captured or not file.is_file():
        return {t:feeds.unknown_earnings(session,now,"UNCAPTURED_AT_CUTOFF") for t in active}
    digest = hashlib.sha256(file.read_bytes()).hexdigest()
    if digest != captured[-1]["details"].get("sha256"):
        return {t:feeds.unknown_earnings(session,now,"CALENDAR_EVIDENCE_TAMPERED") for t in active}
    return feeds.read_earnings(root,session,phase,active,now)


def _session_prices(state: V3State, *, target: str):
    b = state.portfolio.book
    earliest = (date.fromisoformat(b.last_session) + timedelta(days=1)).isoformat() if b.last_session else b.started
    tickers = _required(state) | set(state.watchlist)
    from tradingagents.paper.cli import fetch_daily, forex_for_day
    mandatory = _required(state) | {"SPY", "GBPUSD=X"}
    quotes = fetch_daily(sorted(tickers | {"SPY", "GBPUSD=X"}), earliest, target, required=mandatory)
    # Hard fail on a held/queued ticker's share split or dividend; the existing
    # paper engine models neither adjusted shares nor actual dividend payment.
    # This is an explicit known limitation, never quietly corrupt a return.
    feeds.reject_unmodelled_corporate_actions(_required(state), earliest, target)
    sessions = sorted(x for x in quotes["SPY"] if earliest <= x <= target)
    if not sessions or sessions[-1] != target:
        raise ValueError("Confirmed final SPY daily bar for the target session is missing; no ledger update")
    return quotes, sessions, forex_for_day


def _research_prices(state: V3State, *, target: str):
    """Fetch today's completed candles *after* marking today's portfolio.

    The session-marking loader starts strictly after book.last_session.
    That is correct for replay, but would request TOMORROW after today was
    marked, silently preventing any AI research. Research uses its own
    independently validated target-day fetch, never a partial session.
    """
    from tradingagents.paper.cli import fetch_daily, forex_for_day

    names = set(state.watchlist) | {"SPY", "GBPUSD=X"}
    quotes = fetch_daily(sorted(names), target, target,
                         required={"SPY", "GBPUSD=X"})
    if target not in quotes.get("SPY", {}):
        raise ValueError("The completed SPY bar is unavailable for the research date")
    # A corporate-action surprise must not become a research BUY.
    feeds.reject_unmodelled_corporate_actions(set(state.watchlist), target, target)
    return quotes, [target], forex_for_day


def mark_closed_sessions(state_path: Path, *, now: datetime | None = None,
                         loader=_session_prices) -> dict:
    """Advance the complete portfolio once for each actually observed session.

    Retrospective backfill is flagged and never authorizes NEW long entries.
    State is saved once per good day. On missing held bar/FX, processing stops.
    """
    now = now or datetime.now(timezone.utc)
    target = feeds.session_cutoff(now, "close")
    state = read(state_path)
    if state.portfolio.book.last_session == target:
        return {"status": "already_marked", "session": target, "replayed": 0}
    if state.portfolio.book.last_session and state.portfolio.book.last_session > target:
        raise ValueError("System clock is behind the V3 marked book")
    quotes, sessions, fx_for_day = loader(state, target=target)
    # A provider may return older history along with today's bar; never replay
    # an already marked session, and never silently accept a missing target.
    sessions = sorted(d for d in sessions if not state.portfolio.book.last_session
                      or d > state.portfolio.book.last_session)
    if not sessions or sessions[-1] != target:
        raise ValueError("Latest completed SPY session missing or already marked")
    root = state_path.expanduser().resolve().parent
    count = 0
    for session in sessions:
        work = deepcopy(state)
        active = _required(work)
        # Do not accidentally carry a market order from yesterday if the
        # machine missed the pre-open observation. The conditional core will
        # veto the order on an UNKNOWN earnings snapshot before Book.step.
        is_backfill = session < target
        if is_backfill:
            # CRITICAL: cancel conditional entry BEFORE Book.step can process
            # past opening prices. No retroactive new fills, even if old
            # snapshot files were present when this computer was offline.
            work.cancel_queued("backfill_no_retroactive_new_position")
            work.event("BACKFILL_MODELED_STANDING_RISK", date=session,
                       notice="Modeled resting stops/exits only; NO retroactive new stock entries")
            active = _required(work)
        pre = _validated_calendar(work, root, session, "preopen", active, now)
        preclose = _validated_calendar(work, root, session, "preclose", active, now)
        fx0, fx1 = fx_for_day(quotes["GBPUSD=X"], session)
        bars = {ticker: quotes[ticker][session] for ticker in active
                if ticker in quotes and session in quotes[ticker]}
        price_hash = archive_market_evidence(state_path, session=session, now=now,
                                             bars=bars, fx_open=fx0, fx_close=fx1,
                                             spy_close=quotes["SPY"][session].close)
        prior_events = len(work.portfolio.book.events)
        work.portfolio = work.portfolio.advance(session, bars, fx0, fx1,
                                                quotes["SPY"][session].close,
                                                pre, preclose)
        work.event("SESSION_MARKED", date=session, market_input_sha256=price_hash,
                   backfill=is_backfill, equity_gbp=round(work.portfolio.book.equity(), 2),
                   book_events=len(work.portfolio.book.events)-prior_events,
                   new_order_count=len(work.portfolio.book.orders),
                   note="Simulated historical O/H/L/C prices, not broker executions")
        if not work.can_buy():
            work.cancel_queued("operator_disabled_or_risk_halt")
        atomic_write(state_path, work)
        state = work
        count += 1
    return {"status": "marked", "session": target, "replayed": count,
            "equity_gbp": round(state.portfolio.book.equity(), 2),
            "positions": len(state.portfolio.book.positions),
            "pending": len(state.portfolio.book.orders),
            "halted": state.portfolio.book.halted}


def archive_market_evidence(state_path: Path, *, session: str, now: datetime,
                            bars: dict, fx_open: float, fx_close: float,
                            spy_close: float) -> str:
    """Keep exact simulated price inputs as immutable research evidence.

    A vendor reading isn't exchange-certified. Files are captured after the
    NY market-close gate and cross-linked by SHA-256 in the state audit.
    Re-reading different values for an archived date is a halt, not a silent
    rewrite of historical simulated performance.
    """
    root = state_path.expanduser().resolve().parent
    target = root / "market_evidence" / (session + ".json")
    payload = {
        "schema": "koral-autopilot-daily-input-v1",
        "session": session,
        "captured_at_utc": now.astimezone(timezone.utc).isoformat(),
        "vendor": "YAHOO_FINANCE_SECONDARY_NOT_EXCHANGE_CERTIFIED",
        "bars": {k: asdict(v) for k, v in sorted(bars.items())},
        "gbp_per_usd_open": fx_open,
        "gbp_per_usd_close": fx_close,
        "spy_price_only_close_usd": spy_close,
        "notice": "Modelled daily OHLC only; exchange, corporate actions, and price provenance require further validation",
    }
    data = (json.dumps(payload, sort_keys=True, allow_nan=False, indent=2) + "\n").encode("utf-8")
    h = hashlib.sha256(data).hexdigest()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        old = target.read_bytes()
        if old != data:
            # Captured timestamp differs across retries: compare market values,
            # not the incidental time of the second read.
            previous = json.loads(old)
            current = dict(payload)
            current.pop("captured_at_utc")
            previous.pop("captured_at_utc", None)
            if previous != current:
                raise ValueError("Previously archived market prices have changed; reconcile before continuing")
        return hashlib.sha256(old).hexdigest()
    # Fail closed if a second process simultaneously created a competing file.
    try:
        with target.open("xb") as out:
            out.write(data)
            out.flush()
    except FileExistsError:
        raise ValueError("Market evidence concurrently recorded; manual review") from None
    return h


def _sector_info(ticker: str) -> tuple[str, dict]:
    from tradingagents.dataflows.vendor_gateway import get_yahoo_ticker
    info = get_yahoo_ticker(ticker).info
    if not isinstance(info, dict) or info.get("quoteType") != "EQUITY" or info.get("currency") != "USD":
        raise ValueError("Unverified liquid USD ordinary stock")
    if info.get("financialCurrency") not in {"USD"}:
        raise ValueError("Issuer financial statements not comparable in USD")
    sector = info.get("sector")
    if not isinstance(sector, str) or not sector.strip():
        raise ValueError("Verified sector needed for sector allocation limits")
    if (type(info.get("marketCap")) not in (float,int) or
            info["marketCap"] < 1_000_000_000):
        raise ValueError("Swing Alpha requires at least USD 1bn market capitalization")
    avg_volume = info.get("averageVolume")
    if type(avg_volume) not in (float,int) or avg_volume <= 0:
        raise ValueError("Average trading volume unverified")
    return sector, info


def _graph_factory(root: Path):
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.default_config import DEFAULT_CONFIG
    cfg = DEFAULT_CONFIG.copy()
    cfg["results_dir"] = str(root / "agent_results")
    cfg["memory_log_path"] = str(root / "memory.md")
    return TradingAgentsGraph(config=cfg)


def _research_one(graph, *, ticker: str, session: str, bar,
                  root: Path, state: V3State, sector_info=_sector_info) -> tuple[dict, TradeIntent | None, str]:
    from tradingagents.portfolio import PortfolioContext, Position
    sector, info = sector_info(ticker)
    if info.get("averageVolume") is not None and (info["averageVolume"] * bar.close < 20_000_000):
        raise ValueError("Swing Alpha requires at least USD 20m approximate daily turnover")
    positions = []
    for p in state.portfolio.book.positions.values():
        # PortfolioContext must only contain known actual held positions.
        positions.append(Position(ticker=p["ticker"], quantity=p["shares"],
                                  average_price=p["entry_usd"]))
    context = PortfolioContext(positions=positions)  # GBP cash must NOT be presented as USD
    final_state, rating = graph.propagate(ticker, session, portfolio=context)
    pm = str(final_state.get("final_trade_decision") or "")
    trader = str(final_state.get("trader_investment_plan") or "")
    if not pm.strip() or not trader.strip():
        raise ValueError("No complete portfolio manager and trader decision")
    research = json.dumps({"ticker": ticker, "session": session,
                           "portfolio_manager": pm, "trader": trader,
                           "rating": str(rating),
                           "close_usd": bar.close, "sector": sector,
                           "generated_utc": datetime.now(timezone.utc).isoformat()},
                          sort_keys=True, indent=2, ensure_ascii=True)
    dir_ = root / "reports" / session / ticker
    dir_.mkdir(parents=True, exist_ok=True)
    src = dir_ / "source.json"
    if src.exists():
        raise ValueError("Immutable source receipt already exists; refusing to overwrite")
    src.write_text(research + "\n", encoding="utf-8")
    # A complete archived research report is required before any automated
    # policy approval. If the report writer fails, fail closed on this ticker.
    graph.save_reports(final_state, ticker, save_path=dir_)
    receipt = {"rating": str(rating), "source_sha256": evidence_hash(research + "\n"),
               "source_file": str(src.relative_to(root)),
               "session": session, "decision": "NO_TRADE", "reason": "no valid structured instruction"}
    try:
        proposal = request_proposal(graph, ticker=ticker, session=session, pm=pm, trader=trader)
        if proposal.rating != str(rating):
            raise ValueError("Structured extraction disagrees with original Portfolio Manager rating")
        plan = policy_intent(proposal, ticker=ticker, session=session, final_pm=pm,
                             trader_plan=trader, report=research + "\n", close_usd=bar.close,
                             sector=sector)
    except Exception as exc:
        receipt["reason"] = f"policy_rejected_{type(exc).__name__}: {str(exc)[:200]}"
        return receipt, None, research + "\n"
    receipt["decision"] = "CONDITIONAL_LONG"
    receipt["reason"] = "source_verbatim_and_numeric_policy_validated"
    receipt["intent_id"] = plan.intent_id
    return receipt, plan, research + "\n"


def afterclose_research(state_path: Path, *, now: datetime | None = None,
                       graph_factory=_graph_factory, research_fn=_research_one,
                       loader=_research_prices, max_analyses: int = 3) -> dict:
    """Only after marked today's session. Never re-issues same ticker/day AI action."""
    now = now or datetime.now(timezone.utc)
    target = feeds.session_cutoff(now, "close")
    state = read(state_path)
    if state.portfolio.book.last_session != target:
        raise ValueError("Today's completed market session must be marked first")
    if not state.can_buy():
        return {"status":"research_disabled", "session":target, "reviewed":0}
    if type(max_analyses) is not int or not 1 <= max_analyses <= 5:
        raise ValueError("Invalid daily AI research budget")
    root = state_path.expanduser().resolve().parent
    # A single load is enough: only current completed close is used for decisions.
    quotes, sessions, _ = loader(state, target=target)
    graph = None
    reviewed = 0
    for ticker in state.watchlist[:max_analyses]:
        key = f"{target}:{ticker}"
        state = read(state_path)
        if key in state.ai_receipts:
            continue
        if not state.can_buy():
            break
        if ticker in state.portfolio.book.positions or any(
                rec["plan"]["ticker"] == ticker and rec["status"] in ("WATCHING", "QUEUED")
                for rec in state.portfolio.intents.values()):
            continue
        try:
            if ticker not in quotes or target not in quotes[ticker]:
                raise ValueError("Missing valid completed candidate daily candle")
            if graph is None:
                graph = graph_factory(root)
            receipt, plan, research = research_fn(graph, ticker=ticker, session=target,
                                                  bar=quotes[ticker][target], root=root, state=state)
            if plan is not None:
                state.machine_accept(plan, research, target, "POLICY_VERIFIED")
            receipt["research_generated_utc"] = datetime.now(timezone.utc).isoformat()
        except Exception as exc:
            receipt = {"decision":"NO_TRADE", "session":target,
                       "reason":f"AI_OR_DATA_FAILED_{type(exc).__name__}"}
        state.ai_receipts[key] = receipt
        state.event("AI_RESEARCH_RECEIPT", date=target, ticker=ticker, **receipt)
        atomic_write(state_path, state)
        reviewed += 1
    return {"status":"research_complete", "session":target,
            "reviewed":reviewed, "conditional_intents":sum(
                1 for x in read(state_path).portfolio.intents.values() if x["status"]=="WATCHING")}


def run_afterclose(state_path: Path, *, now: datetime | None = None,
                   with_ai: bool = True) -> dict:
    now = now or datetime.now(timezone.utc)
    marked = mark_closed_sessions(state_path, now=now)
    if with_ai:
        # AI errors never undo already recorded correctly priced stop/position marks.
        marked["ai"] = afterclose_research(state_path, now=now)
    return marked
