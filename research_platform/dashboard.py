"""Local Streamlit dashboard for the research platform.

    tradingagents-platform dashboard        (or: streamlit run research_platform/dashboard.py)

Runs on 127.0.0.1 only. Research and study: nothing here places an order.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from research_platform.config import ANALYSTS, PAPER_DEFAULTS, platform_config, provider_key_status
from research_platform.prices import CachedPrices, today
from research_platform.store import RATINGS
from research_platform.watchlist import default_store, parse_watchlist, run_watchlist

RATING_COLORS = {"Buy": "#1a7f37", "Overweight": "#57ab5a", "Hold": "#8c959f",
                 "Underweight": "#d47e2a", "Sell": "#cf222e"}

st.set_page_config(page_title="TradingAgents Research Platform", layout="wide")


@st.cache_resource
def _prices() -> CachedPrices:
    return CachedPrices()


def _cfg() -> dict:
    return platform_config()


def _store():
    return default_store(_cfg())


def _signals_frame(signals) -> pd.DataFrame:
    return pd.DataFrame([{
        "date": s.date, "ticker": s.ticker, "status": s.status, "rating": s.rating,
        "price": s.price, "size %": None if s.size_pct is None else round(s.size_pct * 100, 2),
        "stop": s.stop_long, "volatility %": None if s.volatility is None else round(s.volatility * 100, 1),
        "models": f"{s.quick_model or ''} / {s.deep_model or ''}", "error": s.error,
    } for s in signals])


# ----------------------------------------------------------------- pages


def page_overview():
    cfg = _cfg()
    st.title("Research platform")
    st.caption("Research and study only. Decisions come from LLM agents and can be wrong; "
               "every number below is computed in Python from recorded decisions and prices.")
    key, present = provider_key_status(cfg)
    st.markdown(f"**Provider:** `{cfg['llm_provider']}` · **quick model:** `{cfg['quick_think_llm']}` · "
                f"**deep model:** `{cfg['deep_think_llm']}` · **API key:** {'set' if present else 'missing'}")
    if key and not present:
        st.warning(f"`{key}` is not set. Add it to the `.env` file in the repo folder to run analyses. "
                   "Scorecard and paper portfolio work on signals already recorded.")
    signals = _store().all()
    ok = [s for s in signals if s.ok]
    c1, c2, c3 = st.columns(3)
    c1.metric("Signals recorded", len(ok))
    c2.metric("Tickers", len({s.ticker for s in ok}))
    c3.metric("Failed runs", sum(s.status == "failed" for s in signals))
    if ok:
        counts = (pd.Series([s.rating for s in ok]).value_counts().reindex(RATINGS, fill_value=0)
                  .rename_axis("rating").reset_index(name="signals"))
        st.subheader("Ratings")
        st.altair_chart(alt.Chart(counts).mark_bar().encode(
            x=alt.X("rating:N", sort=list(RATINGS)), y=alt.Y("signals:Q", axis=alt.Axis(tickMinStep=1)),
            color=alt.Color("rating:N", legend=None, scale=alt.Scale(domain=list(RATING_COLORS),
                                                                     range=list(RATING_COLORS.values())))),
            width="stretch")
        st.subheader("Latest")
        st.dataframe(_signals_frame(sorted(signals, key=lambda s: s.date, reverse=True)[:15]),
                     hide_index=True, width="stretch")


def page_run():
    cfg = _cfg()
    st.title("Run analyses")
    key, present = provider_key_status(cfg)
    if key and not present:
        st.error(f"`{key}` is not set, so the agents cannot run. Add it to `.env` and restart the dashboard.")
    st.caption(f"Each ticker is one full multi-agent run with {cfg['llm_provider']} "
               f"({cfg['quick_think_llm']} / {cfg['deep_think_llm']}). It takes minutes and costs API usage.")
    text = st.text_area("Tickers (one per line or comma separated)", "AAPL\nMSFT\n2222.SR", height=120)
    c1, c2 = st.columns(2)
    run_date = c1.date_input("Analysis date", date.today(), max_value=date.today())
    label = c2.text_input("Label (optional)", "")
    analysts = st.multiselect("Analysts", ANALYSTS, default=["market", "news", "fundamentals", "valuation"])
    rerun = st.checkbox("Run again if already recorded for this date")
    try:
        tickers = parse_watchlist(text)
    except ValueError as exc:
        st.error(str(exc))
        return
    st.write(f"{len(tickers)} tickers: {', '.join(tickers)}")
    if st.button("Run", type="primary", disabled=not (present and tickers and analysts)):
        bar = st.progress(0.0)
        with st.status("Running agents...", expanded=True) as status:
            def progress(i, n, ticker):
                bar.progress((i - 1) / n)
                status.write(f"[{i}/{n}] {ticker}")
            result = run_watchlist(tickers, run_date.strftime("%Y-%m-%d"), cfg, tuple(analysts),
                                   store=_store(), name=label or None, rerun=rerun, progress=progress)
            bar.progress(1.0)
            status.update(label=f"Done: {len(result.ran)} ran, {len(result.skipped)} skipped, "
                                f"{len(result.failed)} failed", state="complete")
        for ticker, error in result.failed:
            st.error(f"{ticker}: {error}")


def page_signals():
    st.title("Signals and reports")
    signals = _store().all()
    if not signals:
        st.info("No signals yet. Run some analyses first.")
        return
    tickers = sorted({s.ticker for s in signals})
    pick = st.selectbox("Ticker", ["All"] + tickers)
    shown = [s for s in signals if pick == "All" or s.ticker == pick]
    st.dataframe(_signals_frame(shown), hide_index=True, width="stretch")
    if pick != "All":
        _price_chart(pick, [s for s in shown if s.ok])
    options = {f"{s.date} · {s.ticker} · {s.rating or s.status}": s for s in reversed(shown)}
    choice = st.selectbox("Open a run", list(options))
    s = options[choice]
    if s.status == "failed":
        st.error(s.error)
        return
    if s.report_path and Path(s.report_path).is_file():
        with st.expander("Full report", expanded=False):
            st.markdown(Path(s.report_path).read_text(encoding="utf-8"))
    st.subheader("Final decision")
    st.markdown(s.decision or "_no decision text_")


def _price_chart(ticker: str, signals):
    if not signals:
        return
    start = (pd.Timestamp(signals[0].date) - timedelta(days=90)).strftime("%Y-%m-%d")
    try:
        closes = _prices()(ticker, start, today())
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Prices unavailable for {ticker}: {exc}")
        return
    if closes.empty:
        return
    line = alt.Chart(closes.rename("close").rename_axis("date").reset_index()).mark_line().encode(
        x="date:T", y=alt.Y("close:Q", scale=alt.Scale(zero=False)))
    marks = pd.DataFrame([{"date": pd.Timestamp(s.date), "close": closes.asof(pd.Timestamp(s.date)),
                           "rating": s.rating} for s in signals]).dropna()
    points = alt.Chart(marks).mark_point(size=120, filled=True).encode(
        x="date:T", y="close:Q", tooltip=["date:T", "rating", "close"],
        color=alt.Color("rating:N", scale=alt.Scale(domain=list(RATING_COLORS),
                                                    range=list(RATING_COLORS.values()))))
    st.altair_chart(line + points, width="stretch")


def page_scorecard():
    from research_platform.scorecard import score

    st.title("Signal scorecard")
    st.caption("Return from the first close after each analysis date, over 5, 21 and 63 trading days, "
               "against the instrument's regional benchmark. Unfinished windows are pending, not estimated.")
    signals = _store().all(only_ok=True)
    if not signals:
        st.info("No signals to score yet.")
        return
    with st.spinner("Fetching prices..."):
        card = score(signals, prices=_prices(), cfg=_cfg())
    summary = card.summary_frame()
    if summary.empty:
        st.info("Every signal is still pending: no horizon has finished trading yet.")
    else:
        horizon = st.radio("Horizon (trading days)", sorted(summary["horizon_days"].unique()), horizontal=True)
        part = summary[summary["horizon_days"] == horizon]
        c1, c2 = st.columns(2)
        c1.metric("Settled signals", int(part["n"].sum()))
        spread = card.spread.get(horizon)
        c2.metric("Bullish minus bearish mean alpha", "n/a" if spread is None else f"{spread:+.2%}")
        chart = alt.Chart(part.dropna(subset=["mean_alpha"])).mark_bar().encode(
            x=alt.X("rating:N", sort=list(RATINGS)), y=alt.Y("mean_alpha:Q", axis=alt.Axis(format="%")),
            color=alt.Color("rating:N", legend=None, scale=alt.Scale(domain=list(RATING_COLORS),
                                                                     range=list(RATING_COLORS.values()))))
        st.altair_chart(chart, width="stretch")
        st.dataframe(part.style.format({"hit_rate": "{:.0%}", "mean_return": "{:+.2%}",
                                        "mean_alpha": "{:+.2%}", "median_alpha": "{:+.2%}"}, na_rep="n/a"),
                     hide_index=True, width="stretch")
        st.caption("Small samples say little: a hit rate over a handful of signals is mostly noise.")
    with st.expander("Every outcome"):
        st.dataframe(card.frame(), hide_index=True, width="stretch")


def page_paper():
    from research_platform.paper import simulate

    st.title("Paper portfolio")
    st.caption("A simulation that follows the recorded signals with their risk-based sizes. "
               "No broker, no orders, no real money.")
    signals = _store().all(only_ok=True)
    if not signals:
        st.info("No signals yet.")
        return
    c1, c2, c3 = st.columns(3)
    cash = c1.number_input("Starting cash", value=PAPER_DEFAULTS["starting_cash"], step=10_000.0, min_value=1_000.0)
    bps = c2.number_input("Commission + slippage per side (bps)", value=PAPER_DEFAULTS["commission_bps"]
                          + PAPER_DEFAULTS["slippage_bps"], min_value=0.0, step=1.0)
    benchmark = c3.text_input("Benchmark", "SPY")
    c1, c2, c3 = st.columns(3)
    use_stops = c1.checkbox("Use recorded ATR stops", value=True)
    ow = c2.slider("Overweight share of a full Buy", 0.0, 1.0, PAPER_DEFAULTS["overweight_scale"])
    uw = c3.slider("Underweight keeps this share", 0.0, 1.0, PAPER_DEFAULTS["underweight_scale"])
    with st.spinner("Simulating..."):
        result = simulate(signals, prices=_prices(), benchmark=benchmark.strip() or None, params={
            "starting_cash": cash, "commission_bps": bps, "slippage_bps": 0.0,
            "use_stops": use_stops, "overweight_scale": ow, "underweight_scale": uw})
    for note in result.notes:
        st.warning(note)
    if not result.stats:
        st.info("Nothing to simulate yet: no signal has a close after its date.")
        return
    s = result.stats
    c = st.columns(3)
    c[0].metric("Total return", f"{s['total_return']:+.2%}")
    c[1].metric(f"Buy-and-hold {result.benchmark}",
                "n/a" if s["benchmark_return"] is None else f"{s['benchmark_return']:+.2%}")
    c[2].metric("Max drawdown", f"{s['max_drawdown']:.2%}")
    c = st.columns(3)
    c[0].metric("Volatility", "n/a" if s["volatility"] is None else f"{s['volatility']:.2%}")
    c[1].metric("Sharpe", "n/a" if s["sharpe"] is None else f"{s['sharpe']:.2f}")
    c[2].metric("Final equity", f"{s['final_equity']:,.0f}")
    curves = pd.DataFrame({"Paper portfolio": result.equity})
    if result.benchmark_equity is not None:
        curves[result.benchmark] = result.benchmark_equity
    long = curves.ffill().rename_axis("date").reset_index().melt("date", var_name="series", value_name="equity")
    st.altair_chart(alt.Chart(long.dropna()).mark_line().encode(
        x="date:T", y=alt.Y("equity:Q", scale=alt.Scale(zero=False)), color="series:N"), width="stretch")
    st.caption(f"Average invested share of the book {s['avg_exposure']:.0%} · costs {s['costs']:,.2f} · "
               f"{s['trades']} trades, {s['stop_exits']} stop exits")
    st.subheader("Trades")
    st.dataframe(result.trades_frame(), hide_index=True, width="stretch")
    if result.positions:
        st.subheader("Open positions (units)")
        st.json(result.positions)


PAGES = {"Overview": page_overview, "Run analyses": page_run, "Signals and reports": page_signals,
         "Scorecard": page_scorecard, "Paper portfolio": page_paper}

choice = st.sidebar.radio("Page", list(PAGES))
st.sidebar.caption("Research only · local · no broker")
PAGES[choice]()
