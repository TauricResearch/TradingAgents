"""TradingAgents in the browser. Launch with `tradingagents ui`.

Three pages share one model-settings sidebar: a live single-ticker analysis,
the saved reports and decision log, and grid backtests. Runs execute on worker
threads (see ``jobs.py``), so the page stays responsive and survives a reload.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import sys
from pathlib import Path

try:
    import cli  # noqa: F401
except ImportError:  # launched with `streamlit run` from a non-installed checkout
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import altair as alt
import pandas as pd
import streamlit as st
from pydantic import ValidationError

from cli.main import _build_run_config
from cli.models import AssetType
from cli.prefs import load_last_run, save_last_run
from cli.utils import (
    _llm_provider_table,
    detect_asset_type,
    is_valid_ticker_input,
    normalize_ticker_symbol,
    resolve_backend_url,
)
from cli.webui.jobs import (
    CANCELLED,
    DONE,
    FAILED,
    RUNNING,
    SECTION_TITLES,
    TEAMS,
    AnalysisJob,
    BacktestJob,
    JobRegistry,
    backtest_summary,
    list_backtests,
    list_saved_reports,
    load_decisions,
    load_report_sections,
)
from tradingagents.backtest import iter_grid
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients.api_key_env import get_api_key_env
from tradingagents.llm_clients.model_catalog import get_model_options
from tradingagents.portfolio import PortfolioContext

st.set_page_config(page_title="TradingAgents", page_icon=":material/candlestick_chart:",
                   layout="wide")

ANALYSTS = {
    "market": "Market",
    "social": "Sentiment",
    "news": "News",
    "fundamentals": "Fundamentals",
}
DEPTHS = {"Shallow": 1, "Medium": 3, "Deep": 5}
LANGUAGES = ["English", "Chinese", "Japanese", "Korean", "Hindi", "Spanish", "Portuguese",
             "French", "German", "Arabic", "Russian", "Custom…"]
REGIONS = {  # provider -> (international, China) as (key, url)
    "qwen": (("qwen", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
             ("qwen-cn", "https://dashscope.aliyuncs.com/compatible-mode/v1")),
    "glm": (("glm", "https://api.z.ai/api/paas/v4/"),
            ("glm-cn", "https://open.bigmodel.cn/api/paas/v4/")),
    "minimax": (("minimax", "https://api.minimax.io/v1"),
                ("minimax-cn", "https://api.minimaxi.com/v1")),
}
EFFORTS = {  # provider -> (selection key, label, choices); "default" = provider default
    "openai": ("openai_reasoning_effort", "Reasoning effort", ["default", "medium", "high", "low"]),
    "anthropic": ("anthropic_effort", "Effort", ["default", "high", "medium", "low"]),
    "google": ("google_thinking_level", "Thinking", ["default", "high", "minimal"]),
}
RATING_COLOR = {"Buy": "green", "Overweight": "green", "Hold": "gray",
                "Underweight": "red", "Sell": "red"}
STATUS_BADGE = {RUNNING: ("Running", "blue", ":material/progress_activity:"),
                DONE: ("Done", "green", ":material/check:"),
                FAILED: ("Failed", "red", ":material/error:"),
                CANCELLED: ("Stopped", "gray", ":material/stop:"),
                "pending": ("Queued", "gray", ":material/schedule:")}
AGENT_STATE = {"completed": "done", "in_progress": "working", "pending": "waiting"}
PIPELINE_CSS = """<style>
.ta-pipeline{display:flex;flex-wrap:wrap;gap:.75rem;margin:.25rem 0 .5rem}
.ta-team{flex:1 1 160px;border:1px solid rgba(128,128,128,.3);border-radius:.6rem;padding:.65rem .85rem}
.ta-team h4{margin:0 0 .35rem;padding:0;font-size:.75rem;font-weight:600;letter-spacing:.04em;
  text-transform:uppercase;opacity:.7}
.ta-team ul{list-style:none;margin:0;padding:0}
.ta-team li{display:flex;align-items:center;gap:.5rem;font-size:.9rem;margin:0;padding:.12rem 0}
.ta-dot{width:.6rem;height:.6rem;border-radius:50%;flex:none;border:2px solid rgba(128,128,128,.6)}
.ta-pending{opacity:.55}
.ta-in_progress{font-weight:600}
.ta-in_progress .ta-dot{border-color:#2a78d6;background:#2a78d6;animation:ta-pulse 1.2s ease-in-out infinite}
.ta-completed .ta-dot{border-color:#0ca30c;background:#0ca30c}
@keyframes ta-pulse{50%{opacity:.35}}
@media (prefers-reduced-motion:reduce){.ta-in_progress .ta-dot{animation:none}}
</style>"""
# Diverging pair for alpha (sign carries the meaning) and the first categorical slots.
POSITIVE, NEGATIVE = "#2a78d6", "#e34948"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]


@st.cache_resource
def registry() -> JobRegistry:
    """Shared by every browser tab on this server, so runs outlive a reload."""
    return JobRegistry()


# --- Sidebar: model settings ----------------------------------------------

def _index(options, value, fallback=0):
    return options.index(value) if value in options else fallback


def _model_picker(provider: str, mode: str, remembered: str | None) -> str:
    label = "Quick-thinking model" if mode == "quick" else "Deep-thinking model"
    try:
        options = get_model_options(provider, mode)
    except KeyError:
        options = []
    values = [v for _, v in options if v != "custom"]
    if not values:  # OpenRouter, Azure deployments, custom endpoints: free text
        return st.text_input(label, value=remembered or "", key=f"{mode}_{provider}_text",
                             placeholder="model id / deployment name").strip()
    names = {v: d for d, v in options}
    choice = st.selectbox(label, values + ["custom"], index=_index(values, remembered),
                          format_func=lambda v: "Custom model id…" if v == "custom" else names[v],
                          key=f"{mode}_{provider}")
    if choice == "custom":
        return st.text_input(f"{label} id", key=f"{mode}_{provider}_custom").strip()
    return choice


def model_settings() -> dict:
    """The sidebar form; returns CLI-shaped selections (minus ticker/date/analysts)."""
    prefs = load_last_run()
    providers = _llm_provider_table()
    keys = [key for _, key, _ in providers]
    display = {key: name for name, key, _ in providers}
    env_provider = os.environ.get("TRADINGAGENTS_LLM_PROVIDER") and DEFAULT_CONFIG["llm_provider"]
    preferred = (env_provider or prefs.get("llm_provider") or DEFAULT_CONFIG["llm_provider"]).lower()

    with st.sidebar:
        st.subheader("Model settings")
        base = st.selectbox("LLM provider", keys, format_func=display.get,
                            index=_index(keys, preferred.removesuffix("-cn")), key="provider")
        provider = base
        menu_url = {k: u for _, k, u in providers}[base]
        if base in REGIONS:
            china = st.toggle("China mainland account", value=preferred.endswith("-cn"),
                              key=f"region_{base}")
            provider, menu_url = REGIONS[base][int(china)]

        remembered = prefs if prefs.get("llm_provider") == provider else {}
        if env_provider == provider:
            remembered = {"quick_think_llm": DEFAULT_CONFIG["quick_think_llm"],
                          "deep_think_llm": DEFAULT_CONFIG["deep_think_llm"]}
        quick = _model_picker(provider, "quick", remembered.get("quick_think_llm"))
        deep = _model_picker(provider, "deep", remembered.get("deep_think_llm"))

        effort = {}
        if provider in EFFORTS:
            key, label, choices = EFFORTS[provider]
            value = st.selectbox(label, choices, index=_index(choices, DEFAULT_CONFIG.get(key)),
                                 format_func=lambda v: "Provider default" if v == "default"
                                 else v.title(), key=f"effort_{provider}")
            effort[key] = None if value == "default" else value

        depth = st.segmented_control("Research depth", list(DEPTHS), key="depth",
                                     default=next((k for k, v in DEPTHS.items()
                                                   if v == prefs.get("research_depth")), "Shallow"),
                                     help="Debate and risk-discussion rounds: 1, 3 or 5.")
        language = st.selectbox("Report language", LANGUAGES, key="language",
                                index=_index(LANGUAGES, prefs.get("output_language"), 0))
        if language == "Custom…":
            language = st.text_input("Language name", key="language_custom").strip() or "English"

        with st.expander("Advanced"):
            backend_url = st.text_input(
                "Backend URL",
                value=resolve_backend_url(provider, menu_url, env_url=DEFAULT_CONFIG["backend_url"])
                or (prefs.get("backend_url") if provider == "openai_compatible" else "") or "",
                key=f"url_{provider}", help="Leave empty for the provider's default endpoint.",
            ).strip() or None
            checkpoint = st.toggle("Checkpoint / resume", value=DEFAULT_CONFIG["checkpoint_enabled"],
                                   key="checkpoint",
                                   help="Save state after each step so a crashed or stopped "
                                   "run resumes where it left off.")
            st.caption(f"Results: `{DEFAULT_CONFIG['results_dir']}`")

        key_ok = _api_key_status(provider)

    return {
        "llm_provider": provider, "backend_url": backend_url,
        "quick_think_llm": quick, "deep_think_llm": deep,
        "research_depth": DEPTHS[depth or "Shallow"], "output_language": language,
        "google_thinking_level": None, "openai_reasoning_effort": None, "anthropic_effort": None,
        **effort, "_checkpoint": checkpoint, "_key_ok": key_ok,
    }


def _api_key_status(provider: str) -> bool:
    from tradingagents.llm_clients.openai_client import OPENAI_COMPATIBLE_PROVIDERS

    env_var = get_api_key_env(provider)
    spec = OPENAI_COMPATIBLE_PROVIDERS.get(provider)
    if env_var is None or (spec is not None and spec.key_optional):
        st.caption(":material/key_off: No API key needed" if provider != "bedrock"
                   else ":material/key: Uses the AWS credential chain")
        return True
    if os.environ.get(env_var):
        st.caption(f":green[:material/key:] `{env_var}` is set")
        return True
    st.warning(f"`{env_var}` is not set.", icon=":material/key:")
    with st.form(f"key_{env_var}", border=False):
        value = st.text_input(env_var, type="password", label_visibility="collapsed",
                              placeholder=f"Paste {env_var}")
        if st.form_submit_button("Use for this session") and value.strip():
            os.environ[env_var] = value.strip()
            st.rerun()
    st.caption("Kept in this server's memory only. Put it in `.env` to keep it.")
    return False


def run_config(selections: dict) -> dict | None:
    if not selections["_key_ok"]:
        st.error("Set the provider's API key in the sidebar first.")
        return None
    if not selections["quick_think_llm"] or not selections["deep_think_llm"]:
        st.error("Choose both models in the sidebar first.")
        return None
    return _build_run_config(selections, selections["_checkpoint"])


def _portfolio(upload) -> tuple[PortfolioContext | None, bool]:
    if upload is None:
        return None, True
    try:
        return PortfolioContext.model_validate(json.loads(upload.getvalue())), True
    except (ValueError, ValidationError) as exc:
        st.error(f"That portfolio file is not usable: {exc}")
        return None, False


PORTFOLIO_HELP = ('JSON like {"cash": 10000, "currency": "USD", "positions": '
                  '[{"ticker": "AAPL", "quantity": 20, "average_price": 180}]}')


# --- Page: Analyze ---------------------------------------------------------

def analyze_page():
    selections = st.session_state["selections"]
    st.title("Analyze a ticker")
    st.caption("Analyst team → Research debate → Trader → Risk debate → Portfolio manager")

    with st.form("analyze"):
        c1, c2 = st.columns(2)
        ticker = c1.text_input("Ticker", value="SPY", help="With exchange suffix when needed: "
                               "SPY, 0700.HK, RELIANCE.NS, BTC-USD")
        trade_date = c2.date_input("Analysis date", value=dt.date.today(),
                                   max_value=dt.date.today())
        remembered = load_last_run().get("analysts") or list(ANALYSTS)
        analysts = st.pills("Analysts", list(ANALYSTS), format_func=ANALYSTS.get,
                            selection_mode="multi", default=[a for a in remembered if a in ANALYSTS])
        upload = st.file_uploader("Portfolio (optional)", type="json", help=PORTFOLIO_HELP)
        submitted = st.form_submit_button("Run analysis", type="primary",
                                          icon=":material/play_arrow:")

    if submitted:
        _start_analysis(selections, ticker, trade_date, analysts, upload)

    jobs = registry().of_type(AnalysisJob)
    if not jobs:
        st.info("Runs you start appear here, with each agent's progress as it happens.",
                icon=":material/info:")
        return
    ids = [j.id for j in jobs]
    current = st.session_state.get("analysis_id")
    if len(jobs) > 1:
        current = st.selectbox("Run", ids, index=_index(ids, current),
                               format_func=lambda i: _job_title(registry().get(i)))
    job = registry().get(current) or jobs[0]
    st.divider()
    live_run(job)


def _job_title(job) -> str:
    return f"{job.label} — {STATUS_BADGE[job.status][0]}"


def _start_analysis(selections, ticker, trade_date, analysts, upload):
    if not is_valid_ticker_input(ticker):
        st.error("Tickers use letters, digits and . _ - ^ = only.")
        return
    ticker = normalize_ticker_symbol(ticker.strip() or "SPY")
    asset_type = detect_asset_type(ticker)
    analysts = list(analysts or [])
    if asset_type == AssetType.CRYPTO and "fundamentals" in analysts:
        analysts.remove("fundamentals")
        st.toast("Crypto has no fundamentals; skipping that analyst.", icon=":material/info:")
    if not analysts:
        st.error("Pick at least one analyst.")
        return
    portfolio, ok = _portfolio(upload)
    config = run_config(selections)
    if config is None or not ok:
        return
    save_last_run({**selections, "analysts": analysts})
    job = AnalysisJob(ticker, trade_date.isoformat(), asset_type.value, analysts, config, portfolio)
    registry().add(job.start())
    st.session_state["analysis_id"] = job.id


def live_run(job: AnalysisJob):
    @st.fragment(run_every=1.0 if job.active else None)
    def panel():
        snap = job.snapshot()
        if snap["status"] != st.session_state.get(f"seen_{job.id}"):
            first = f"seen_{job.id}" not in st.session_state
            st.session_state[f"seen_{job.id}"] = snap["status"]
            if not first and not job.active:
                st.rerun()  # stop polling once the run settles

        head, action = st.columns([5, 2], vertical_alignment="center")
        with head:
            text, color, icon = STATUS_BADGE[snap["status"]]
            st.subheader(job.label)
            st.badge(text, color=color, icon=icon)
        if job.active and action.button("Stop", icon=":material/stop:", key=f"stop_{job.id}",
                                        help="Stops after the current step."):
            job.cancel()
            st.toast("Stopping after the current step…")

        _decision(job, snap)

        stats = snap["stats"]
        done = sum(1 for s in snap["sections"].values() if s)
        m = st.columns(5)
        m[0].metric("Elapsed", _duration(snap["elapsed"]))
        m[1].metric("Reports", f"{done}/{len(snap['sections'])}")
        m[2].metric("LLM calls", stats["llm_calls"])
        m[3].metric("Tool calls", stats["tool_calls"])
        m[4].metric("Tokens", _k(stats["tokens_in"] + stats["tokens_out"]),
                    help=f"{stats['tokens_in']:,} in · {stats['tokens_out']:,} out")

        _pipeline(snap["agent_status"])

        reports, activity = st.tabs([":material/description: Reports",
                                     ":material/terminal: Activity"])
        with reports:
            _live_reports(job, snap["sections"])
        with activity:
            _activity(snap)

    panel()


def _decision(job, snap):
    if snap["status"] == FAILED:
        st.error(snap["error"].split("\n\n", 1)[0], icon=":material/error:")
        with st.expander("Traceback"):
            st.code(snap["error"], language="text")
    if snap["status"] != DONE:
        return
    rating = snap["rating"]
    color = RATING_COLOR.get(rating, "orange")
    with st.container(border=True):
        left, right = st.columns([3, 1], vertical_alignment="center")
        left.markdown(f"#### Portfolio manager's call: :{color}[**{rating}**]")
        if rating not in RATING_COLOR:
            left.caption("No rating could be read from the final decision, so it is logged "
                         "for review. Read the decision below and judge it yourself.")
        path = snap["report_path"]
        if path and Path(path).exists():
            right.download_button("Report", Path(path).read_text(encoding="utf-8"),
                                  file_name=f"{job.ticker}_{job.trade_date}.md",
                                  icon=":material/download:", key=f"dl_{job.id}",
                                  help="Download the complete report as Markdown")
            st.caption(f"Saved to {Path(path).parent}")


def _pipeline(agent_status: dict):
    teams = []
    for team, agents in TEAMS.items():
        rows = "".join(
            f'<li class="ta-{agent_status[a]}" aria-label="{a}: {AGENT_STATE[agent_status[a]]}" '
            f'title="{AGENT_STATE[agent_status[a]]}"><span class="ta-dot"></span>{html.escape(a)}</li>'
            for a in agents if a in agent_status
        )
        if rows:
            teams.append(f'<div class="ta-team"><h4>{team}</h4><ul>{rows}</ul></div>')
    st.html(PIPELINE_CSS + f'<div class="ta-pipeline">{"".join(teams)}</div>')


def _live_reports(job, sections: dict):
    ready = [s for s, text in sections.items() if text]
    if not ready:
        st.caption("Reports appear here as each agent finishes.")
        return
    # Follow the newest section until the user picks one themselves.
    key, auto = f"section_{job.id}", f"section_auto_{job.id}"
    current = st.session_state.get(key)
    if current not in ready or current == st.session_state.get(auto):
        st.session_state[key] = st.session_state[auto] = ready[-1]
    choice = st.segmented_control("Section", ready, format_func=SECTION_TITLES.get, key=key,
                                  label_visibility="collapsed")
    with st.container(border=True):
        st.markdown(sections[choice or ready[-1]])


def _activity(snap):
    rows = [{"time": t, "kind": kind, "detail": str(content)[:400]}
            for t, kind, content in snap["messages"]]
    rows += [{"time": t, "kind": "Tool", "detail": f"{name}({_args(args)})"}
             for t, name, args in snap["tool_calls"]]
    if not rows:
        st.caption("Nothing yet.")
        return
    frame = pd.DataFrame(rows).iloc[::-1].sort_values("time", ascending=False, kind="stable")
    st.dataframe(frame, hide_index=True, use_container_width=True, height=420,
                 column_config={"detail": st.column_config.TextColumn(width="large")})


def _args(args) -> str:
    return ", ".join(f"{k}={v}" for k, v in args.items()) if isinstance(args, dict) else str(args)


def _duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s" if m else f"{s}s"


def _k(n: int) -> str:
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


# --- Page: Reports ---------------------------------------------------------

def reports_page():
    st.title("Reports")
    saved, log = st.tabs([":material/folder_open: Saved reports", ":material/list_alt: Decision log"])
    with saved:
        _saved_reports()
    with log:
        _decision_log(DEFAULT_CONFIG["memory_log_path"], key="live_log")


def _saved_reports():
    reports = list_saved_reports(DEFAULT_CONFIG["results_dir"])
    if not reports:
        st.info(f"No saved reports yet under `{DEFAULT_CONFIG['results_dir']}`.",
                icon=":material/info:")
        return
    tickers = sorted({r.ticker for r in reports})
    c1, c2 = st.columns([1, 3])
    ticker = c1.selectbox("Ticker", ["All"] + tickers)
    shown = [r for r in reports if ticker in ("All", r.ticker)]
    report = c2.selectbox("Report", shown, format_func=lambda r: r.label)
    sections = load_report_sections(report)
    st.caption(f"`{report.path}` · modified {report.modified:%Y-%m-%d %H:%M}")
    if report.kind == "report":
        st.download_button("Download", report.path.read_text(encoding="utf-8"),
                           file_name=f"{report.ticker}_{report.path.parent.name}.md",
                           icon=":material/download:")
    if not sections:
        st.caption("This report is empty.")
        return
    for tab, (_, body) in zip(st.tabs([t for t, _ in sections]), sections, strict=True):
        with tab:
            st.markdown(body)


def _decision_log(log_path, key: str):
    rows = load_decisions(log_path)
    if not rows:
        st.info("No decisions logged yet. Each finished run adds one; it settles against "
                "the benchmark on the next run for that ticker.", icon=":material/info:")
        return
    frame = pd.DataFrame(rows).iloc[::-1].reset_index(drop=True)
    tickers = sorted(frame["ticker"].unique())
    pick = st.multiselect("Tickers", tickers, key=f"{key}_tickers", placeholder="All tickers")
    if pick:
        frame = frame[frame["ticker"].isin(pick)].reset_index(drop=True)
    event = st.dataframe(
        frame[["date", "ticker", "rating", "status", "return", "alpha", "holding"]],
        hide_index=True, use_container_width=True, on_select="rerun",
        selection_mode="single-row", key=f"{key}_table",
        column_config={
            "return": st.column_config.NumberColumn("Return", format="percent"),
            "alpha": st.column_config.NumberColumn("Alpha", format="percent",
                                                   help="Return minus the benchmark's"),
        },
    )
    selected = event.selection.rows
    if selected:
        row = frame.iloc[selected[0]]
        with st.container(border=True):
            st.markdown(f"**{row['ticker']} · {row['date']} · {row['rating']}**")
            st.markdown(row["decision"] or "_No decision text._")
            if row["reflection"]:
                st.markdown("**Reflection**")
                st.markdown(row["reflection"])
    else:
        st.caption("Select a row to read its decision and reflection.")


# --- Page: Backtest --------------------------------------------------------

def backtest_page():
    selections = st.session_state["selections"]
    st.title("Backtest")
    st.caption("Runs the full analysis for every ticker on every date in the grid, then scores "
               "each call's alpha against the benchmark. Each cell is a complete run, so "
               "cost and time grow with the grid.")

    with st.form("backtest"):
        c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
        tickers = c1.text_input("Tickers", value="NVDA,AAPL", help="Comma-separated")
        today = dt.date.today()
        start = c2.date_input("From", value=today - dt.timedelta(days=60), max_value=today)
        end = c3.date_input("To", value=today - dt.timedelta(days=14), max_value=today)
        every = c4.number_input("Every n days", min_value=1, value=7)
        analysts = st.pills("Analysts", list(ANALYSTS), format_func=ANALYSTS.get,
                            selection_mode="multi", default=list(ANALYSTS))
        c6, c7 = st.columns(2)
        asset_type = c6.selectbox("Asset type", ["stock", "crypto"])
        run_id = c7.text_input("Run id (optional)", help="Reuse one to continue an earlier sweep.")
        upload = st.file_uploader("Portfolio (optional, held constant)", type="json",
                                  help=PORTFOLIO_HELP)
        submitted = st.form_submit_button("Start backtest", type="primary",
                                          icon=":material/play_arrow:")

    if submitted:
        _start_backtest(selections, tickers, start, end, every, analysts, asset_type, run_id,
                        upload)

    for job in registry().of_type(BacktestJob):
        if job.active or job.id == st.session_state.get("backtest_id"):
            _backtest_progress(job)

    st.divider()
    _backtest_results()


def _start_backtest(selections, tickers, start, end, every, analysts, asset_type, run_id, upload):
    names = [normalize_ticker_symbol(t.strip()) for t in tickers.split(",") if t.strip()]
    if not names or not all(is_valid_ticker_input(t) for t in names):
        st.error("Enter comma-separated tickers, e.g. NVDA,AAPL.")
        return
    analysts = [a for a in (analysts or []) if not (asset_type == "crypto" and a == "fundamentals")]
    if not analysts:
        st.error("Pick at least one analyst.")
        return
    try:
        dates = iter_grid(start.isoformat(), end.isoformat(), int(every))
    except ValueError as exc:
        st.error(str(exc))
        return
    portfolio, ok = _portfolio(upload)
    config = run_config(selections)
    if config is None or not ok:
        return
    kwargs = {"run_id": run_id.strip()} if run_id.strip() else {}
    try:
        job = BacktestJob(names, dates, config, analysts, asset_type, portfolio, **kwargs)
    except ValueError as exc:
        st.error(str(exc))
        return
    registry().add(job.start())
    st.session_state["backtest_id"] = job.id
    st.session_state["backtest_view"] = job.run_id


def _backtest_progress(job: BacktestJob):
    @st.fragment(run_every=3.0 if job.active else None)
    def panel():
        if not job.active and st.session_state.get(f"seen_{job.id}") == RUNNING:
            st.session_state[f"seen_{job.id}"] = job.status
            st.rerun()
        st.session_state[f"seen_{job.id}"] = job.status
        text, color, icon = STATUS_BADGE[job.status]
        with st.container(border=True):
            st.markdown(f"**{job.label}**")
            st.badge(text, color=color, icon=icon)
            logged = min(job.cells_logged(), job.total_cells)
            st.progress(logged / job.total_cells if job.total_cells else 1.0,
                        text=f"{logged} of {job.total_cells} cells · {_duration(job.elapsed())}")
            if job.active:
                st.caption("A sweep runs to the end once started. Stopping the server stops it; "
                           "start again with the same run id to continue where it left off.")
            if job.status == FAILED:
                st.error(job.error.split("\n\n", 1)[0])
            if job.result is not None:
                r = job.result
                st.caption(f"Ran {r.cells_run} cells, skipped {r.skipped}.")
                for ticker, date, reason in r.failures:
                    st.warning(f"{ticker} {date}: {reason}")
                for ticker, reason in r.settlement_failures:
                    st.warning(f"Could not settle {ticker}: {reason}")

    panel()


def _backtest_results():
    st.subheader("Results")
    runs = list_backtests(DEFAULT_CONFIG)
    if not runs:
        st.info("Finished backtests appear here.", icon=":material/info:")
        return
    names = [p.name for p in runs]
    name = st.selectbox("Backtest run", names, index=_index(names, st.session_state.get("backtest_view")))
    log_path = runs[names.index(name)] / "trading_memory.md"
    summary = backtest_summary(log_path)

    m = st.columns(3)
    m[0].metric("Settled cells", summary.resolved)
    m[1].metric("Pending", summary.pending, help="Holding window not over yet; re-run to settle.")
    m[2].metric("Unscored", summary.unscored, help="No rating could be read from the decision.")

    if summary.by_rating:
        order = {r: i for i, r in enumerate(RATING_COLOR)}
        scores = pd.DataFrame([
            {"rating": rating, "cells": s.count, "hit rate": s.hit_rate, "mean alpha": s.mean_alpha}
            for rating, s in sorted(summary.by_rating.items(), key=lambda kv: order.get(kv[0], 99))
        ])
        left, right = st.columns(2)
        with left:
            st.markdown("**Mean alpha by rating**")
            st.altair_chart(_alpha_bars(scores), use_container_width=True)
        with right:
            st.markdown("**Alpha of each settled call**")
            cells = pd.DataFrame(load_decisions(log_path))
            cells = cells[cells["alpha"].notna()]
            st.altair_chart(_alpha_dots(cells), use_container_width=True)
        table = scores.assign(**{"hit rate": scores["hit rate"] * 100,
                                 "mean alpha": scores["mean alpha"] * 100})
        st.dataframe(table, hide_index=True, use_container_width=True, column_config={
            "hit rate": st.column_config.NumberColumn(
                format="%.0f%%", help="Share of calls whose alpha had the sign the rating "
                "claimed. Hold claims no direction, so it has none."),
            "mean alpha": st.column_config.NumberColumn(format="%+.2f%%"),
        })
        st.caption(f"Alpha is measured over {summary.holding} after each analysis date. One "
                   "model sampling per cell, so these figures are indicative, not repeatable.")

    with st.expander("Every cell"):
        _decision_log(log_path, key=f"bt_{name}")


def _alpha_bars(scores: pd.DataFrame):
    bars = alt.Chart(scores).mark_bar(cornerRadiusEnd=4, size=22).encode(
        y=alt.Y("rating:N", sort=list(scores["rating"]), title=None),
        x=alt.X("mean alpha:Q", title="Mean alpha", axis=alt.Axis(format="%")),
        color=alt.condition("datum['mean alpha'] >= 0", alt.value(POSITIVE), alt.value(NEGATIVE)),
        tooltip=["rating", "cells", alt.Tooltip("mean alpha:Q", format="+.2%"),
                 alt.Tooltip("hit rate:Q", format=".0%")],
    )
    zero = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color="#8a8984").encode(x="x:Q")
    return (bars + zero).properties(height=max(140, 44 * len(scores)))


def _alpha_dots(cells: pd.DataFrame):
    cells = cells.assign(date=pd.to_datetime(cells["date"]))
    tooltip = ["ticker", alt.Tooltip("date:T", format="%Y-%m-%d"), "rating",
               alt.Tooltip("alpha:Q", format="+.1%")]
    y = alt.Y("alpha:Q", title="Alpha", axis=alt.Axis(format="%"))
    zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color="#8a8984").encode(y="y:Q")
    tickers = sorted(cells["ticker"].unique())
    if len(tickers) <= len(SERIES):
        dots = alt.Chart(cells).mark_circle(size=80, opacity=0.9, stroke="white", strokeWidth=2).encode(
            x=alt.X("date:T", title=None), y=y, tooltip=tooltip,
            color=alt.Color("ticker:N", scale=alt.Scale(domain=tickers, range=SERIES[:len(tickers)]),
                            legend=alt.Legend(orient="top", title=None)),
        )
        return (dots + zero).properties(height=280)
    # More tickers than distinguishable colors: one small panel per ticker instead.
    dots = alt.Chart().mark_circle(size=64, color=POSITIVE).encode(
        x=alt.X("date:T", title=None), y=y, tooltip=tooltip)
    return alt.layer(dots, zero, data=cells).properties(height=120, width=220).facet(
        facet=alt.Facet("ticker:N", title=None), columns=2)


# --- App -------------------------------------------------------------------

st.session_state["selections"] = model_settings()
page = st.navigation([
    st.Page(analyze_page, title="Analyze", icon=":material/query_stats:", default=True),
    st.Page(reports_page, title="Reports", icon=":material/article:", url_path="reports"),
    st.Page(backtest_page, title="Backtest", icon=":material/history:", url_path="backtest"),
])
page.run()
