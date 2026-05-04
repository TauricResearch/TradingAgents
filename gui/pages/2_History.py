"""History page — browse all past analysis runs.

Combines two sources: the SQLite ``runs`` table (rows for runs the GUI
launched) and on-disk JSON state logs (which include CLI-launched runs).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from gui import brief as brief_mod
from gui import chat, charts, export, storage
from gui.log_browser import discover_logs, load_archive_full, load_log
from gui.md_utils import safe_md

st.set_page_config(page_title="History · TradingAgents", layout="wide")
storage.init_db()

st.title("Run history")

# Build a unified table. The DB is keyed by run_id; on-disk archived files
# carry the run_id in their filename so we can join cleanly. Legacy
# canonical files (CLI runs from before archival was added) join only by
# (ticker, date) and don't have stats.
db_by_run_id = {r["run_id"]: r for r in storage.list_runs(limit=10_000)}
db_by_ticker_date = {}
for r in db_by_run_id.values():
    # Latest DB row per (ticker, date) for joining canonical files.
    db_by_ticker_date.setdefault((r["ticker"], r["trade_date"]), r)

disk_runs = discover_logs()

show_legacy = st.toggle(
    "Show legacy CLI runs (canonical files duplicated by an archive)",
    value=False,
    help="Pre-archive runs are still listed; flip this on to also show "
         "the canonical file for any run that also has a per-run archive.",
)

rows = []
seen_run_ids = set()

# Archived rows first (one per run, immutable).
for entry in disk_runs:
    if entry.get("kind") == "canonical_legacy" and not show_legacy:
        continue
    if entry.get("kind") == "canonical_legacy":
        # Legacy (duplicated) — show but flag.
        db = db_by_ticker_date.get((entry["ticker"], entry["trade_date"]), {})
        rows.append({
            "ticker": entry["ticker"],
            "trade_date": entry["trade_date"],
            "run_ts": "(legacy)",
            "decision": db.get("decision") or "—",
            "provider": db.get("provider") or "(cli)",
            "deep_model": db.get("deep_model") or "—",
            "tokens_in": db.get("tokens_in") or 0,
            "tokens_out": db.get("tokens_out") or 0,
            "status": "legacy",
            "log_path": entry["log_path"],
            "run_id": "",
        })
        continue

    if entry.get("kind") == "archive":
        rid = entry.get("run_id", "")
        seen_run_ids.add(rid)
        db = db_by_run_id.get(rid, {}) or db_by_ticker_date.get((entry["ticker"], entry["trade_date"]), {})
        rows.append({
            "ticker": entry["ticker"],
            "trade_date": entry["trade_date"],
            "run_ts": entry.get("run_ts") or "",
            "decision": db.get("decision") or "—",
            "provider": db.get("provider") or "(cli)",
            "deep_model": db.get("deep_model") or "—",
            "tokens_in": db.get("tokens_in") or 0,
            "tokens_out": db.get("tokens_out") or 0,
            "status": db.get("status") or "done",
            "log_path": entry["log_path"],
            "run_id": rid,
        })
        continue

    # kind == "canonical" (no archive exists, e.g. older CLI run).
    db = db_by_ticker_date.get((entry["ticker"], entry["trade_date"]), {})
    rows.append({
        "ticker": entry["ticker"],
        "trade_date": entry["trade_date"],
        "run_ts": "",
        "decision": db.get("decision") or "—",
        "provider": db.get("provider") or "(cli)",
        "deep_model": db.get("deep_model") or "—",
        "tokens_in": db.get("tokens_in") or 0,
        "tokens_out": db.get("tokens_out") or 0,
        "status": db.get("status") or "done",
        "log_path": entry["log_path"],
        "run_id": db.get("run_id") or "",
    })

# Pull in DB runs that don't yet have a log file (running, failed).
for rid, db in db_by_run_id.items():
    if rid in seen_run_ids:
        continue
    if db.get("log_path") and Path(db["log_path"]).exists():
        # Already covered by a disk entry.
        continue
    rows.append({
        "ticker": db["ticker"],
        "trade_date": db["trade_date"],
        "run_ts": "",
        "decision": db.get("decision") or "—",
        "provider": db.get("provider") or "—",
        "deep_model": db.get("deep_model") or "—",
        "tokens_in": db.get("tokens_in") or 0,
        "tokens_out": db.get("tokens_out") or 0,
        "status": db.get("status") or "—",
        "log_path": db.get("log_path") or "",
        "run_id": rid,
    })

if not rows:
    st.info("No runs yet. Open **Run** in the sidebar to start one.")
    st.stop()

df = pd.DataFrame(rows)

# Filter bar.
col1, col2, col3 = st.columns(3)
ticker_filter = col1.text_input("Filter by ticker (substring)").strip().upper()
decision_filter = col2.multiselect("Decision", sorted(df["decision"].unique()))
status_filter = col3.multiselect("Status", sorted(df["status"].unique()))

view = df.copy()
if ticker_filter:
    view = view[view["ticker"].str.contains(ticker_filter, case=False, na=False)]
if decision_filter:
    view = view[view["decision"].isin(decision_filter)]
if status_filter:
    view = view[view["status"].isin(status_filter)]

view = view.sort_values(["trade_date", "ticker"], ascending=[False, True])

st.dataframe(
    view[["ticker", "trade_date", "run_ts", "decision", "provider", "deep_model",
          "tokens_in", "tokens_out", "status"]],
    use_container_width=True,
    hide_index=True,
)

st.divider()
st.subheader("Open a run")

# Pick from filtered view. Include the run timestamp so multiple runs of
# the same ticker+date are distinguishable.
def _label(r):
    parts = [r['ticker'], r['trade_date']]
    if r.get('run_ts'):
        parts.append(r['run_ts'])
    parts.append(f"→ {r['decision']}")
    return " · ".join(parts)

options = [_label(r) for _, r in view.iterrows()]
if not options:
    st.caption("Nothing matches the filters above.")
    st.stop()

choice = st.selectbox("Select a run", options, index=0)
chosen = view.iloc[options.index(choice)]

log_path = chosen["log_path"]
if not log_path or not Path(log_path).exists():
    st.warning("State log file not found on disk.")
    st.stop()

state = load_log(log_path)
if state is None:
    st.error("Could not parse the state log.")
    st.stop()

st.markdown(f"**{chosen['ticker']}** · {chosen['trade_date']}  ·  decision **{chosen['decision']}**")

# ---- Plain-English brief (the headline, top of page) ------------------
st.subheader("📋 Plain-English brief")
brief_caption_col, brief_btn_col = st.columns([4, 1])
brief_caption_col.caption(
    "What to do, when, and what to watch — distilled from the full analysis. "
    "Generated by the quick-think model and cached per run."
)

run_id_for_brief = chosen.get("run_id") or ""
cached = brief_mod.get_cached_brief(run_id_for_brief) if run_id_for_brief else None

if brief_btn_col.button("🔄 Regenerate", help="Force a fresh brief", disabled=not run_id_for_brief):
    try:
        new_brief = brief_mod.generate_brief(state, {**export_meta, "decision": chosen.get("decision")})
        brief_mod.store_brief(run_id_for_brief, new_brief)
        cached = new_brief
        st.rerun()
    except Exception as e:
        st.error(f"Brief generation failed: {e}")

if cached is None:
    if not run_id_for_brief:
        st.info(
            "Briefs require a run_id — legacy CLI runs don't have one. "
            "Re-run the same ticker+date through the GUI to get a brief."
        )
    else:
        if st.button("✨ Generate plain-English brief", type="primary"):
            try:
                with st.spinner("Distilling the analysis…"):
                    new_brief = brief_mod.generate_brief(
                        state, {**export_meta, "decision": chosen.get("decision")},
                    )
                    brief_mod.store_brief(run_id_for_brief, new_brief)
                    st.rerun()
            except Exception as e:
                st.error(f"Brief generation failed: {e}")
else:
    st.markdown(safe_md(cached.to_markdown()))

st.divider()

# ---- Performance vs index --------------------------------------------
st.subheader("📈 vs S&P 500 / Nasdaq-100")

bench_col1, bench_col2, bench_col3 = st.columns([1, 1, 1])
with bench_col1:
    days_back = st.select_slider(
        "Look-back (days)", options=[30, 90, 180, 365], value=90,
        key="hist_days_back",
    )
with bench_col2:
    days_forward = st.select_slider(
        "Look-forward (days)", options=[30, 90, 180, 365], value=180,
        key="hist_days_forward",
    )
with bench_col3:
    show_qqq = st.checkbox("Include QQQ", value=True, key="hist_show_qqq")

benchmarks = ["SPY"] + (["QQQ"] if show_qqq else [])
with st.spinner("Pulling price data from Yahoo…"):
    df = charts.build_comparison_frame(
        chosen["ticker"], chosen["trade_date"],
        days_back=days_back, days_forward=days_forward,
        benchmarks=benchmarks,
    )
if df is None or df.empty:
    st.caption("Couldn't fetch price data for this ticker / window.")
else:
    st.caption(f"Indexed to **100** at the trade date ({chosen['trade_date']}).")
    st.line_chart(df, height=320)

returns_df = charts.realised_returns_table(chosen["ticker"], chosen["trade_date"])
if returns_df is not None:
    st.markdown("**Realised return windows** (vs SPY, post-trade-date):")
    st.dataframe(returns_df, use_container_width=True, hide_index=True)
else:
    st.caption(
        "Trade date is too recent for realised-return windows. "
        "Come back after at least a week."
    )

st.divider()

# ---- Export panel -----------------------------------------------------
# Build the meta dict the export module expects, joining DB fields where we have them.
db_row = storage.get_run(chosen["run_id"]) if chosen.get("run_id") else None
export_meta = {
    "ticker": chosen["ticker"],
    "trade_date": chosen["trade_date"],
    "decision": chosen.get("decision"),
    "provider": chosen.get("provider"),
    "deep_model": chosen.get("deep_model"),
    "quick_model": (db_row or {}).get("quick_model"),
    "started_at": (db_row or {}).get("started_at"),
    "completed_at": (db_row or {}).get("completed_at"),
    "tokens_in": chosen.get("tokens_in", 0),
    "tokens_out": chosen.get("tokens_out", 0),
    "run_id": chosen.get("run_id") or "",
    "log_path": log_path,
}

st.subheader("📦 Files for this run")
st.caption(
    f"Saved under `{export.EXPORTS_DIR}/{chosen['ticker']}/`. "
    "All four formats are produced automatically the first time you open a run; "
    "re-export with the button below to refresh them with the latest brief."
)

# Auto-export on first view: produce md, html, pdf if they don't exist yet.
prior_exports = export.list_exports_for_run(export_meta)
need_export = not all(prior_exports.get(ext) for ext in ("md", "html", "pdf"))
if need_export and chosen.get("run_id"):
    try:
        if not prior_exports.get("md"):
            export.write_export(export.render_markdown(state, export_meta), export_meta, "md")
        if not prior_exports.get("html"):
            export.write_export(export.render_html(state, export_meta), export_meta, "html")
        if not prior_exports.get("pdf") and export.has_pdf_support():
            pdf_bytes = export.render_pdf(state, export_meta)
            if pdf_bytes:
                export.write_export(pdf_bytes, export_meta, "pdf")
        prior_exports = export.list_exports_for_run(export_meta)
    except Exception as e:
        st.warning(f"Auto-export skipped: {e}")

# Render a row per file with size, open-file link, and download button.
def _file_row(label: str, ext: str, path: Path | None, *, helptext: str = "") -> None:
    f1, f2, f3, f4 = st.columns([2, 4, 1, 1])
    f1.markdown(f"**{label}**")
    if path and path.exists():
        size_kb = path.stat().st_size / 1024
        f2.code(str(path), language="text")
        try:
            data = path.read_bytes()
        except OSError:
            data = b""
        f3.download_button(
            f"⬇ {ext}", data=data,
            mime={"json": "application/json", "md": "text/markdown",
                  "html": "text/html", "pdf": "application/pdf"}.get(ext, "application/octet-stream"),
            file_name=path.name,
            use_container_width=True, key=f"dl_{ext}_file",
            help=helptext or f"Download the {ext} file ({size_kb:.1f} KB)",
        )
        # Streamlit can't open the OS file manager from a button, but
        # showing the parent dir as a triple-clickable code block is the
        # next-best thing.
        f4.caption(f"{size_kb:.1f} KB")
    else:
        f2.caption("(not generated yet)")
        f3.caption("—")
        f4.caption("—")


# JSON: read the actual archive file (already on disk).
_file_row("JSON archive", "json", Path(log_path),
          helptext="Richest format — metadata + state + tool trace. Drop into Claude.ai for follow-up Q&A.")
_file_row("Markdown", "md", prior_exports.get("md"),
          helptext="Plain-text report — paste anywhere.")
_file_row("Standalone HTML", "html", prior_exports.get("html"),
          helptext="Self-contained interactive report — emailable, viewable offline.")
if export.has_pdf_support():
    _file_row("PDF", "pdf", prior_exports.get("pdf"),
              helptext="Print-friendly archive document.")
else:
    f1, f2, _, _ = st.columns([2, 4, 1, 1])
    f1.markdown("**PDF**")
    f2.caption("Disabled — install with `pip install xhtml2pdf`")

# Re-export button (forces fresh files including any updated brief).
exp_col1, exp_col2 = st.columns([1, 5])
if exp_col1.button("🔄 Re-export all", key="reexport_all"):
    export.write_export(export.render_markdown(state, export_meta), export_meta, "md")
    export.write_export(export.render_html(state, export_meta), export_meta, "html")
    if export.has_pdf_support():
        pdf_bytes = export.render_pdf(state, export_meta)
        if pdf_bytes:
            export.write_export(pdf_bytes, export_meta, "pdf")
    st.success("Re-exported. Reload this run to see the new files.")
    st.rerun()
exp_col2.caption(
    "Re-export creates fresh timestamped files — previous exports are kept."
)

st.divider()

tab_labels = [
    ("Market", state.get("market_report")),
    ("Sentiment", state.get("sentiment_report")),
    ("News", state.get("news_report")),
    ("Fundamentals", state.get("fundamentals_report")),
    ("Bull vs Bear", None),
    ("Research Mgr", (state.get("investment_debate_state") or {}).get("judge_decision")),
    ("Trader Plan", state.get("trader_investment_decision") or state.get("investment_plan")),
    ("Risk Debate", None),
    ("Final Decision", state.get("final_trade_decision")),
]
tabs = st.tabs([t[0] for t in tab_labels])

for tab, (label, content) in zip(tabs, tab_labels):
    with tab:
        if label == "Bull vs Bear":
            d = state.get("investment_debate_state") or {}
            bcol, ecol = st.columns(2)
            with bcol:
                st.subheader("Bull")
                st.markdown(safe_md(d.get("bull_history")) or "_(no content)_")
            with ecol:
                st.subheader("Bear")
                st.markdown(safe_md(d.get("bear_history")) or "_(no content)_")
        elif label == "Risk Debate":
            d = state.get("risk_debate_state") or {}
            for side, key in (("Aggressive", "aggressive_history"),
                              ("Conservative", "conservative_history"),
                              ("Neutral", "neutral_history")):
                st.subheader(side)
                st.markdown(safe_md(d.get(key)) or "_(no content)_")
            if d.get("judge_decision"):
                st.subheader("Risk Judge")
                st.markdown(safe_md(d["judge_decision"]))
        else:
            st.markdown(safe_md(content) or "_(no content)_")

# ---- Chat with this run ----------------------------------------------
# Shows for any run that has a real run_id (so the chat can be persisted
# in SQLite and reloaded later). Legacy CLI runs without a DB row use a
# synthetic id derived from the log path so chats still work in-session.
chat_key = chosen.get("run_id") or f"legacy-{abs(hash(log_path))}"

st.divider()
st.subheader("Chat about this run")
st.caption(
    f"Asks the **quick-think** model ({chat.quick_think_label()}) with the full "
    "analysis as context. Conversation is saved per-run."
)

# Pull tool trace if this is a v1 archive — chat module gets richer context.
archive_full = load_archive_full(log_path) or {}
tool_trace = archive_full.get("tool_trace") or []

# Load prior messages from SQLite (or in-memory legacy fallback).
hist_key = f"chat_hist_{chat_key}"
if hist_key not in st.session_state:
    if chosen.get("run_id"):
        prior = storage.list_chat_messages(chat_key)
        st.session_state[hist_key] = [
            {"role": m["role"], "content": m["content"]} for m in prior
        ]
    else:
        st.session_state[hist_key] = []

# Render history.
for msg in st.session_state[hist_key]:
    with st.chat_message(msg["role"]):
        st.markdown(safe_md(msg["content"]))

# Input.
question = st.chat_input("Ask anything about this analysis…")
if question:
    # User turn
    st.session_state[hist_key].append({"role": "user", "content": question})
    if chosen.get("run_id"):
        storage.add_chat_message(run_id=chat_key, role="user", content=question)
    with st.chat_message("user"):
        st.markdown(safe_md(question))

    # Assistant turn (streamed)
    with st.chat_message("assistant"):
        history_for_llm = st.session_state[hist_key][:-1]  # exclude the just-added question
        meta_for_chat = {**export_meta, "decision": chosen.get("decision")}
        stream = chat.stream_response(state, meta_for_chat, history_for_llm,
                                      question, tool_trace=tool_trace)
        # st.write_stream renders chunks token-by-token AND returns the joined text.
        response_text = st.write_stream(lambda: (safe_md(t) for t in stream))

    st.session_state[hist_key].append({"role": "assistant", "content": response_text})
    if chosen.get("run_id"):
        from gui import chat as _chat_mod
        storage.add_chat_message(run_id=chat_key, role="assistant",
                                 content=response_text,
                                 model=_chat_mod.quick_think_label())

# Manage controls.
mc1, mc2 = st.columns([1, 5])
if mc1.button("🗑 Clear chat", help="Delete the saved conversation for this run"):
    if chosen.get("run_id"):
        storage.clear_chat(chat_key)
    st.session_state[hist_key] = []
    st.rerun()

# ---- Notes -----------------------------------------------------------
if chosen.get("run_id"):
    st.divider()
    st.subheader("Notes for this run")
    notes = storage.list_notes(run_id=chosen["run_id"])
    if not notes:
        st.caption("No notes yet.")
    for n in notes:
        with st.expander(f"{n['title']}  ·  {n['updated_at']}"):
            st.markdown(safe_md(n["body"]))
            if n.get("tags"):
                st.caption(f"Tags: {n['tags']}")

st.caption(f"State log: `{log_path}`")
