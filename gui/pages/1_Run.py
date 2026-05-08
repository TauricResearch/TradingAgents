"""Run page — kick off an analysis and watch it stream live."""

from __future__ import annotations

import time
from datetime import date
from typing import Any, Dict, List

import streamlit as st

from gui import brief as brief_mod
from gui import chat, charts, runner, storage
from gui.config import (
    DATA_VENDORS,
    LLM_PROVIDERS,
    PROVIDER_KEYS,
    PROVIDER_LABELS,
    export_env,
    load as load_config,
    model_choices_for,
)
from gui.md_utils import safe_md

st.set_page_config(page_title="Run · TradingAgents", layout="wide")
storage.init_db()

# ---------------------------------------------------------------------------
# Session state — survives Streamlit reruns. The runner handle, the
# accumulated event list, the section content, and the current run_id all
# live here so a rerun (e.g. user clicks anything) doesn't lose progress.
# ---------------------------------------------------------------------------
SS = st.session_state
SS.setdefault("runner_handle", None)
SS.setdefault("run_events", [])
SS.setdefault("run_sections", {})        # section_key -> latest markdown
SS.setdefault("run_debates", {"bull": [], "bear": [], "aggressive": [],
                              "conservative": [], "neutral": []})
SS.setdefault("run_stats", {"llm_calls": 0, "tool_calls": 0,
                            "tokens_in": 0, "tokens_out": 0})
SS.setdefault("run_log", [])              # raw chunk lines (scrolling)
SS.setdefault("run_id", None)
SS.setdefault("run_meta", {})
SS.setdefault("run_decision", None)
SS.setdefault("run_error", None)
SS.setdefault("run_warning", None)


def _reset() -> None:
    SS.runner_handle = None
    SS.run_events = []
    SS.run_sections = {}
    SS.run_debates = {"bull": [], "bear": [], "aggressive": [], "conservative": [], "neutral": []}
    SS.run_stats = {"llm_calls": 0, "tool_calls": 0, "tokens_in": 0, "tokens_out": 0}
    SS.run_log = []
    SS.run_id = None
    SS.run_meta = {}
    SS.run_decision = None
    SS.run_error = None
    SS.run_warning = None


def _ingest(events: List[Dict[str, Any]]) -> None:
    """Apply incoming events to session state."""
    for ev in events:
        SS.run_events.append(ev)
        t = ev.get("type")
        if t == "section":
            SS.run_sections[ev["key"]] = ev.get("content", "")
        elif t == "debate":
            SS.run_debates.setdefault(ev["side"], []).append(ev.get("content", ""))
        elif t == "risk":
            SS.run_debates.setdefault(ev["side"], []).append(ev.get("content", ""))
        elif t == "stats":
            SS.run_stats = {k: ev.get(k, SS.run_stats.get(k, 0))
                            for k in ("llm_calls", "tool_calls", "tokens_in", "tokens_out")}
        elif t == "chunk":
            SS.run_log.append(f"[{ev.get('role','?')}] {ev.get('content','')}")
            SS.run_log = SS.run_log[-200:]
        elif t == "tool_start":
            SS.run_log.append(f"[tool→{ev.get('tool','?')}] {ev.get('input','')}")
            SS.run_log = SS.run_log[-200:]
        elif t == "tool_end":
            SS.run_log.append(f"[tool←] {ev.get('preview','')}")
            SS.run_log = SS.run_log[-200:]
        elif t == "done":
            SS.run_decision = ev.get("decision")
            # If a warning landed earlier (e.g. canonical log write failed
            # but archive succeeded), the run is still done — clear any
            # error UI from before so we don't render red over a success.
            SS.run_error = None
            if SS.run_id:
                storage.update_run_stats(
                    SS.run_id,
                    llm_calls=SS.run_stats["llm_calls"],
                    tool_calls=SS.run_stats["tool_calls"],
                    tokens_in=SS.run_stats["tokens_in"],
                    tokens_out=SS.run_stats["tokens_out"],
                )
                # Prefer the per-run archive path (immutable, never
                # overwritten by future runs of the same ticker+date).
                storage.finalize_run(
                    SS.run_id,
                    decision=ev.get("decision"),
                    log_path=ev.get("archive_path") or ev.get("report_path"),
                )
        elif t == "warning":
            SS.run_warning = ev.get("message", "")
        elif t == "error":
            SS.run_error = ev.get("message", "unknown error")
            if SS.run_id:
                storage.finalize_run(SS.run_id, decision=None, log_path=None,
                                     error=SS.run_error)


def _config_form() -> Dict[str, Any] | None:
    cfg = load_config()
    defaults = cfg.get("defaults", {})

    # Provider sits OUTSIDE the form so changing it triggers a rerun and
    # rebuilds the model dropdowns. (Form widgets only rerun on submit.)
    provider = st.selectbox(
        "LLM provider", LLM_PROVIDERS,
        index=LLM_PROVIDERS.index(defaults.get("llm_provider", "openai")),
        format_func=lambda p: PROVIDER_LABELS.get(p, p),
        key="run_provider",
        help="Change this first — model lists below will update.",
    )

    with st.form("run_form"):
        c1, c2 = st.columns(2)
        ticker = c1.text_input("Ticker", value="NVDA",
                               help="Symbol with optional exchange suffix (e.g. AAPL, TD.TO)").strip().upper()
        trade_date = c2.date_input("Trade date", value=date.today(),
                                   format="YYYY-MM-DD")

        deep_values, deep_labels = model_choices_for(provider, "deep")
        quick_values, quick_labels = model_choices_for(provider, "quick")
        saved_deep = defaults.get("deep_think_llm", "")
        saved_quick = defaults.get("quick_think_llm", "")
        if saved_deep and saved_deep not in deep_values:
            deep_values = [saved_deep] + deep_values
        if saved_quick and saved_quick not in quick_values:
            quick_values = [saved_quick] + quick_values

        c4, c5 = st.columns(2)
        deep_model = c4.selectbox(
            "Deep-think model", deep_values,
            index=deep_values.index(saved_deep) if saved_deep in deep_values else 0,
            format_func=lambda v: deep_labels.get(v, v),
            accept_new_options=True,
            key=f"run_deep_{provider}",
            help="Used for high-stakes nodes (Research Mgr, Trader, PM). Pick from catalog or type any id.",
        )
        quick_model = c5.selectbox(
            "Quick-think model", quick_values,
            index=quick_values.index(saved_quick) if saved_quick in quick_values else 0,
            format_func=lambda v: quick_labels.get(v, v),
            accept_new_options=True,
            key=f"run_quick_{provider}",
            help="Used for analysts and tool routing. Pick from catalog or type any id.",
        )

        c6, c7 = st.columns(2)
        debate_rounds = c6.slider("Bull/Bear debate rounds", 1, 5,
                                  value=int(defaults.get("max_debate_rounds", 1)))
        risk_rounds = c7.slider("Risk discussion rounds", 1, 5,
                                value=int(defaults.get("max_risk_discuss_rounds", 1)))

        st.markdown("**Data vendors**")
        v_default = defaults.get("data_vendors", {})
        cv1, cv2, cv3, cv4 = st.columns(4)
        v_core = cv1.selectbox("Stock data", DATA_VENDORS,
                               index=DATA_VENDORS.index(v_default.get("core_stock_apis", "yfinance")))
        v_tech = cv2.selectbox("Technical", DATA_VENDORS,
                               index=DATA_VENDORS.index(v_default.get("technical_indicators", "yfinance")))
        v_fund = cv3.selectbox("Fundamentals", DATA_VENDORS,
                               index=DATA_VENDORS.index(v_default.get("fundamental_data", "yfinance")))
        v_news = cv4.selectbox("News", DATA_VENDORS,
                               index=DATA_VENDORS.index(v_default.get("news_data", "yfinance")))

        submit = st.form_submit_button("▶ Analyze", type="primary",
                                       disabled=SS.runner_handle is not None)
        if not submit:
            return None

        # Validate that the chosen provider has an API key.
        env_name = PROVIDER_KEYS.get(provider)
        if env_name:
            from gui.config import resolve_api_key
            if not resolve_api_key(provider):
                st.error(
                    f"No API key found for {PROVIDER_LABELS[provider]}. "
                    f"Set ${env_name} in your environment or add it on the **Settings** page."
                )
                return None

        return {
            "ticker": ticker,
            "trade_date": str(trade_date),
            "llm_provider": provider,
            "deep_think_llm": deep_model,
            "quick_think_llm": quick_model,
            "max_debate_rounds": debate_rounds,
            "max_risk_discuss_rounds": risk_rounds,
            "data_vendors": {
                "core_stock_apis": v_core,
                "technical_indicators": v_tech,
                "fundamental_data": v_fund,
                "news_data": v_news,
            },
        }


def _start_run(job: Dict[str, Any]) -> None:
    _reset()
    SS.run_id = storage.new_run_id()
    SS.run_meta = job
    storage.create_run(
        run_id=SS.run_id,
        ticker=job["ticker"],
        trade_date=job["trade_date"],
        provider=job["llm_provider"],
        deep_model=job["deep_think_llm"],
        quick_model=job["quick_think_llm"],
        debate_rounds=job["max_debate_rounds"],
        risk_rounds=job["max_risk_discuss_rounds"],
        vendors=job["data_vendors"],
    )
    # Stamp run_id into the job so the worker can use it for the archive
    # path — this is what makes re-runs of the same ticker+date never
    # overwrite previous transcripts.
    job_with_id = dict(job)
    job_with_id["run_id"] = SS.run_id
    cfg = load_config()
    env = export_env(cfg)
    SS.runner_handle = runner.launch(job_with_id, env=env)


# ---------------------------------------------------------------------------
# Page layout
# ---------------------------------------------------------------------------

st.title("Run analysis")

job = _config_form()
if job:
    _start_run(job)

# Drain queue + render. While running, schedule a rerun loop.
if SS.runner_handle is not None:
    new_events = SS.runner_handle.poll_events()
    _ingest(new_events)

# Status row
status_col, stats_col, action_col = st.columns([2, 2, 1])
with status_col:
    if SS.runner_handle is None and SS.run_decision is None and SS.run_error is None:
        st.info("Configure a run above and hit **Analyze**.")
    elif SS.run_error:
        st.error(f"Run failed: {SS.run_error}")
    elif SS.run_decision is not None:
        st.success(f"Decision: **{SS.run_decision}**")
        if SS.run_warning:
            st.warning(SS.run_warning)
    elif SS.runner_handle and SS.runner_handle.is_running():
        meta = SS.run_meta or {}
        # Figure out roughly where we are in the pipeline.
        order = [
            ("market_report", "Market analyst"),
            ("sentiment_report", "Sentiment analyst"),
            ("news_report", "News analyst"),
            ("fundamentals_report", "Fundamentals analyst"),
            ("research_judge", "Research manager"),
            ("trader_investment_plan", "Trader"),
            ("final_trade_decision", "Final decision"),
        ]
        latest_section = None
        for key, label in order:
            if SS.run_sections.get(key):
                latest_section = label
        if (SS.run_debates.get("bull") or SS.run_debates.get("bear")) \
                and not SS.run_sections.get("research_judge"):
            latest_section = "Bull/Bear debate"
        if any(SS.run_debates.get(k) for k in ("aggressive", "conservative", "neutral")) \
                and not SS.run_sections.get("final_trade_decision"):
            latest_section = "Risk debate"
        stage = f" · last finished: **{latest_section}**" if latest_section else ""
        st.info(f"Analyzing **{meta.get('ticker','?')}** for {meta.get('trade_date','?')}…{stage}")
    elif SS.runner_handle and not SS.runner_handle.is_running():
        st.warning("Worker exited without emitting `done` — see the log below.")

with stats_col:
    s = SS.run_stats
    st.caption(
        f"LLM calls: **{s['llm_calls']}**  ·  Tool calls: **{s['tool_calls']}**  ·  "
        f"Tokens in/out: **{s['tokens_in']:,} / {s['tokens_out']:,}**"
    )

with action_col:
    if SS.runner_handle and SS.runner_handle.is_running():
        if st.button("✕ Cancel", type="secondary"):
            SS.runner_handle.cancel()
            SS.run_error = "Cancelled by user."
    elif SS.run_decision is not None or SS.run_error:
        if st.button("Clear", type="secondary"):
            if SS.runner_handle:
                SS.runner_handle.cleanup()
            _reset()
            st.rerun()

# ---------------------------------------------------------------------------
# Tabs filled as sections complete.
# ---------------------------------------------------------------------------
sections = SS.run_sections
debates = SS.run_debates

tab_labels = [
    ("Market", "market_report"),
    ("Sentiment", "sentiment_report"),
    ("News", "news_report"),
    ("Fundamentals", "fundamentals_report"),
    ("Bull vs Bear", None),
    ("Research Mgr", "research_judge"),
    ("Trader Plan", "trader_investment_plan"),
    ("Risk Debate", None),
    ("Final Decision", "final_trade_decision"),
    ("Live Log", None),
]
tabs = st.tabs([f"✓ {lbl}" if (key and sections.get(key)) else lbl
                for lbl, key in tab_labels])

for tab, (label, key) in zip(tabs, tab_labels):
    with tab:
        if label == "Bull vs Bear":
            bcol, ecol = st.columns(2)
            with bcol:
                st.subheader("Bull")
                if debates.get("bull"):
                    st.markdown(safe_md(debates["bull"][-1]))
                else:
                    st.caption("Waiting…")
            with ecol:
                st.subheader("Bear")
                if debates.get("bear"):
                    st.markdown(safe_md(debates["bear"][-1]))
                else:
                    st.caption("Waiting…")
        elif label == "Risk Debate":
            for side in ("aggressive", "conservative", "neutral"):
                st.subheader(side.title())
                if debates.get(side):
                    st.markdown(safe_md(debates[side][-1]))
                else:
                    st.caption("Waiting…")
        elif label == "Live Log":
            log = "\n".join(SS.run_log[-100:]) or "(no events yet)"
            st.code(log[-20_000:], language="text")
        elif key:
            content = sections.get(key)
            if content:
                st.markdown(safe_md(content))
            else:
                st.caption("Waiting…")

# ---------------------------------------------------------------------------
# Plain-English brief — appears as soon as a decision lands. This is the
# headline "what should I do" view.
# ---------------------------------------------------------------------------
if SS.run_id and SS.run_decision is not None:
    st.divider()
    st.subheader("📋 Plain-English brief")
    st.caption(
        "What to do, when, and what to watch — distilled by the quick-think model. "
        "Generated once and cached; click Regenerate to refresh."
    )

    chat_state_for_brief = {
        "market_report": SS.run_sections.get("market_report"),
        "sentiment_report": SS.run_sections.get("sentiment_report"),
        "news_report": SS.run_sections.get("news_report"),
        "fundamentals_report": SS.run_sections.get("fundamentals_report"),
        "trader_investment_plan": SS.run_sections.get("trader_investment_plan"),
        "final_trade_decision": SS.run_sections.get("final_trade_decision"),
        "investment_debate_state": {
            "bull_history": SS.run_debates["bull"][-1] if SS.run_debates.get("bull") else "",
            "bear_history": SS.run_debates["bear"][-1] if SS.run_debates.get("bear") else "",
            "judge_decision": SS.run_sections.get("research_judge", ""),
        },
        "risk_debate_state": {
            "aggressive_history": SS.run_debates["aggressive"][-1] if SS.run_debates.get("aggressive") else "",
            "conservative_history": SS.run_debates["conservative"][-1] if SS.run_debates.get("conservative") else "",
            "neutral_history": SS.run_debates["neutral"][-1] if SS.run_debates.get("neutral") else "",
        },
    }
    brief_meta = {
        "ticker": (SS.run_meta or {}).get("ticker"),
        "trade_date": (SS.run_meta or {}).get("trade_date"),
        "decision": SS.run_decision,
        "run_id": SS.run_id,
    }

    cached_brief = brief_mod.get_cached_brief(SS.run_id)
    bcol1, bcol2 = st.columns([5, 1])
    if bcol2.button("🔄 Regenerate", key="run_regen_brief"):
        try:
            new_brief = brief_mod.generate_brief(chat_state_for_brief, brief_meta)
            brief_mod.store_brief(SS.run_id, new_brief)
            cached_brief = new_brief
            st.rerun()
        except Exception as e:
            st.error(f"Brief generation failed: {e}")

    if cached_brief is None:
        if bcol1.button("✨ Generate plain-English brief", type="primary",
                        key="run_gen_brief"):
            try:
                with st.spinner("Distilling the analysis…"):
                    new_brief = brief_mod.generate_brief(chat_state_for_brief, brief_meta)
                    brief_mod.store_brief(SS.run_id, new_brief)
                    st.rerun()
            except Exception as e:
                st.error(f"Brief generation failed: {e}")
    else:
        st.markdown(safe_md(cached_brief.to_markdown()))

# ---------------------------------------------------------------------------
# vs index quick view
# ---------------------------------------------------------------------------
if SS.run_id and SS.run_decision is not None:
    st.divider()
    st.subheader("📈 vs S&P 500 / Nasdaq-100")
    ticker_for_chart = (SS.run_meta or {}).get("ticker")
    date_for_chart = (SS.run_meta or {}).get("trade_date")
    if ticker_for_chart and date_for_chart:
        with st.spinner("Pulling price data from Yahoo…"):
            chart_df = charts.build_comparison_frame(
                ticker_for_chart, date_for_chart,
                days_back=90, days_forward=180,
                benchmarks=["SPY", "QQQ"],
            )
        if chart_df is not None and not chart_df.empty:
            st.caption(f"Indexed to **100** at the trade date ({date_for_chart}).")
            st.line_chart(chart_df, height=300)
        else:
            st.caption("Couldn't fetch price data for this ticker / window.")
        rt = charts.realised_returns_table(ticker_for_chart, date_for_chart)
        if rt is not None:
            st.markdown("**Realised return windows** (vs SPY, post-trade-date):")
            st.dataframe(rt, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Chat about this run — full Q&A panel.
# ---------------------------------------------------------------------------
if SS.run_id and SS.run_decision is not None:
    st.divider()
    st.subheader("Chat about this run")
    st.caption(
        f"Asks the **quick-think** model ({chat.quick_think_label()}) with the full "
        "analysis as context. Saved per-run; pick this run up later from **History**."
    )

    chat_state = {
        "market_report": SS.run_sections.get("market_report"),
        "sentiment_report": SS.run_sections.get("sentiment_report"),
        "news_report": SS.run_sections.get("news_report"),
        "fundamentals_report": SS.run_sections.get("fundamentals_report"),
        "trader_investment_plan": SS.run_sections.get("trader_investment_plan"),
        "final_trade_decision": SS.run_sections.get("final_trade_decision"),
        "investment_debate_state": {
            "bull_history": SS.run_debates["bull"][-1] if SS.run_debates.get("bull") else "",
            "bear_history": SS.run_debates["bear"][-1] if SS.run_debates.get("bear") else "",
            "judge_decision": SS.run_sections.get("research_judge", ""),
        },
        "risk_debate_state": {
            "aggressive_history": SS.run_debates["aggressive"][-1] if SS.run_debates.get("aggressive") else "",
            "conservative_history": SS.run_debates["conservative"][-1] if SS.run_debates.get("conservative") else "",
            "neutral_history": SS.run_debates["neutral"][-1] if SS.run_debates.get("neutral") else "",
        },
    }
    chat_meta = {
        "ticker": (SS.run_meta or {}).get("ticker"),
        "trade_date": (SS.run_meta or {}).get("trade_date"),
        "decision": SS.run_decision,
        "provider": (SS.run_meta or {}).get("llm_provider"),
        "deep_model": (SS.run_meta or {}).get("deep_think_llm"),
        "quick_model": (SS.run_meta or {}).get("quick_think_llm"),
        "run_id": SS.run_id,
    }

    hist_key = f"chat_hist_{SS.run_id}"
    if hist_key not in SS:
        SS[hist_key] = []

    for m in SS[hist_key]:
        with st.chat_message(m["role"]):
            st.markdown(safe_md(m["content"]))

    q = st.chat_input("Ask anything about this analysis…")
    if q:
        SS[hist_key].append({"role": "user", "content": q})
        storage.add_chat_message(run_id=SS.run_id, role="user", content=q)
        with st.chat_message("user"):
            st.markdown(safe_md(q))
        with st.chat_message("assistant"):
            history_for_llm = SS[hist_key][:-1]
            stream = chat.stream_response(chat_state, chat_meta, history_for_llm, q)
            response_text = st.write_stream(lambda: (safe_md(t) for t in stream))
        SS[hist_key].append({"role": "assistant", "content": response_text})
        storage.add_chat_message(run_id=SS.run_id, role="assistant",
                                 content=response_text,
                                 model=chat.quick_think_label())

# ---------------------------------------------------------------------------
# Quick note attach.
# ---------------------------------------------------------------------------
if SS.run_id:
    st.divider()
    with st.expander("Add a note about this run"):
        with st.form("note_form", clear_on_submit=True):
            note_title = st.text_input("Title")
            note_body = st.text_area("Body (markdown)", height=120)
            note_tags = st.text_input("Tags (comma-separated)")
            if st.form_submit_button("Save note"):
                if note_title.strip() and note_body.strip():
                    storage.add_note(
                        title=note_title.strip(),
                        body=note_body,
                        ticker=(SS.run_meta or {}).get("ticker"),
                        run_id=SS.run_id,
                        tags=note_tags or None,
                    )
                    st.success("Saved.")
                else:
                    st.warning("Title and body are required.")

# ---------------------------------------------------------------------------
# While the worker is alive, schedule a rerun every ~600ms to keep the UI
# refreshing. Streamlit reruns the whole page when we call st.rerun(), but
# session_state preserves the runner handle and accumulated events.
# ---------------------------------------------------------------------------
if SS.runner_handle is not None and SS.runner_handle.is_running():
    # Every rerun re-imports modules from Python's path; on NAS-hosted
    # repos that's painful, so we keep the loop tick at ~1.5s. Streaming
    # still feels responsive because the live log still updates per tick.
    time.sleep(1.5)
    st.rerun()
elif SS.runner_handle is not None and not SS.runner_handle.is_running():
    # Final drain after the process exits.
    final = SS.runner_handle.poll_events()
    if final:
        _ingest(final)
        st.rerun()
