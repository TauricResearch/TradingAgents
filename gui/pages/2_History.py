"""History page — browse all past analysis runs.

Combines two sources: the SQLite ``runs`` table (rows for runs the GUI
launched) and on-disk JSON state logs (which include CLI-launched runs).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from gui import export, storage
from gui.log_browser import discover_logs, load_log
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

with st.expander("📦 Export this run", expanded=False):
    st.caption(
        f"All exports go to `{export.EXPORTS_DIR}/<TICKER>/`. Each export gets a fresh "
        "timestamped filename — re-exporting the same run never overwrites a previous file."
    )
    ec1, ec2, ec3 = st.columns(3)
    if ec1.button("Save Markdown", use_container_width=True):
        path = export.write_export(export.render_markdown(state, export_meta), export_meta, "md")
        st.success(f"Saved to `{path}`")
    if ec2.button("Save standalone HTML", use_container_width=True):
        path = export.write_export(export.render_html(state, export_meta), export_meta, "html")
        st.success(f"Saved to `{path}`")
    if ec3.button("Save PDF", use_container_width=True, disabled=not export.has_pdf_support(),
                  help=None if export.has_pdf_support()
                       else "Install xhtml2pdf: pip install xhtml2pdf"):
        pdf = export.render_pdf(state, export_meta)
        if pdf:
            path = export.write_export(pdf, export_meta, "pdf")
            st.success(f"Saved to `{path}`")
        else:
            st.error("PDF support not installed. Run: pip install xhtml2pdf")

    # Also offer in-browser download of the rendered formats (no disk write).
    st.divider()
    st.caption("Or download directly without saving to disk:")
    dc1, dc2, dc3 = st.columns(3)
    md_text = export.render_markdown(state, export_meta)
    dc1.download_button(
        "⬇ Markdown", data=md_text, mime="text/markdown",
        file_name=f"{export.export_basename(export_meta)}.md",
        use_container_width=True, key="dl_md",
    )
    html_text = export.render_html(state, export_meta)
    dc2.download_button(
        "⬇ HTML", data=html_text, mime="text/html",
        file_name=f"{export.export_basename(export_meta)}.html",
        use_container_width=True, key="dl_html",
    )
    if export.has_pdf_support():
        pdf_bytes = export.render_pdf(state, export_meta)
        dc3.download_button(
            "⬇ PDF", data=pdf_bytes or b"", mime="application/pdf",
            file_name=f"{export.export_basename(export_meta)}.pdf",
            use_container_width=True, key="dl_pdf",
            disabled=not pdf_bytes,
        )
    else:
        dc3.button("⬇ PDF", disabled=True, use_container_width=True,
                   help="Install xhtml2pdf to enable")

    # Show prior exports for this run, if any.
    prior = export.list_exports_for_run(export_meta)
    if prior:
        st.divider()
        st.caption("Previous exports of this run still on disk:")
        for ext, p in prior.items():
            st.write(f"`.{ext}` → `{p}`")

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

# Notes attached to this run.
if chosen.get("run_id"):
    st.divider()
    st.subheader("Notes for this run")
    notes = storage.list_notes(run_id=chosen["run_id"])
    if not notes:
        st.caption("No notes yet.")
    for n in notes:
        with st.expander(f"{n['title']}  ·  {n['updated_at']}"):
            st.markdown(n["body"])
            if n.get("tags"):
                st.caption(f"Tags: {n['tags']}")

st.caption(f"State log: `{log_path}`")
