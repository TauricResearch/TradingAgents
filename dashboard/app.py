from __future__ import annotations

try:
    from dashboard.report_review import (
        DASHBOARD_DISCLAIMER,
        REPORT_ARTIFACTS,
        format_data_quality_markdown,
        list_dates,
        list_symbols,
        read_json_artifact,
        render_markdown_artifact,
        report_bundle_path,
        report_root,
    )
except ModuleNotFoundError:
    from report_review import (
        DASHBOARD_DISCLAIMER,
        REPORT_ARTIFACTS,
        format_data_quality_markdown,
        list_dates,
        list_symbols,
        read_json_artifact,
        render_markdown_artifact,
        report_bundle_path,
        report_root,
    )


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="IndiaMarketAgents", layout="wide")
    st.title("IndiaMarketAgents")
    st.warning(DASHBOARD_DISCLAIMER)
    st.caption("Read-only saved report review. No broker connections, order placement, or live trading controls.")

    root = report_root()
    symbols = list_symbols(root)
    if not symbols:
        st.info("No saved reports found under reports/<SYMBOL>/<DATE>/.")
        st.stop()

    symbol = st.sidebar.selectbox("Ticker", symbols)
    dates = list_dates(root, symbol)
    if not dates:
        st.info("No dated report folders found for this ticker.")
        st.stop()

    date = st.sidebar.selectbox("Date", dates)
    base = report_bundle_path(root, symbol, date)

    summary_col, decision_col, quality_col = st.columns(3)
    summary_col.metric("Ticker", symbol)
    decision_col.metric("Date", date)
    quality_col.metric("Scope", "India-only")

    tabs = st.tabs([artifact.label for artifact in REPORT_ARTIFACTS])
    for tab, artifact in zip(tabs, REPORT_ARTIFACTS, strict=True):
        with tab:
            if artifact.kind == "data_quality_json":
                st.markdown(format_data_quality_markdown(read_json_artifact(base / artifact.filename)))
            else:
                st.markdown(render_markdown_artifact(base, artifact))

    st.sidebar.caption(f"Report folder: {base}")
    st.sidebar.warning(DASHBOARD_DISCLAIMER)


if __name__ == "__main__":
    main()
