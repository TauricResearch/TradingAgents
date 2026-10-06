"""Streamlit interface for running TradingAgents analyses."""

from datetime import date

import streamlit as st

from cli.models import AnalystType
from cli.prompts import detect_asset_type, filter_analysts_for_asset_type, parse_ticker
from tradingagents.agents.rating import run_rating
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.llm_clients.api_key_env import get_api_key_env
from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS, get_model_options


ANALYST_LABELS = {
    "market": "Market",
    "social": "Sentiment",
    "news": "News",
    "fundamentals": "Fundamentals",
}

st.set_page_config(
    page_title="TradingAgents",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root {
        --ink: #f5f5f7;
        --muted: #a1a1a6;
        --accent: #0a84ff;
        --surface: #1c1c1e;
        --surface-raised: #2c2c2e;
        --border: #38383a;
    }
    .stApp {
        color: var(--ink);
        background:
            radial-gradient(ellipse at 88% 0%, rgba(10, 132, 255, 0.09), transparent 34%),
            linear-gradient(155deg, #171719 0%, #101012 54%, #09090a 100%);
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif;
    }
    h1, h2, h3 { color: var(--ink); }
    h1 { font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", sans-serif; }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1b1b1d 0%, #151517 100%);
        border-right: 1px solid #303033;
    }
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] [data-testid="stWidgetLabel"] {
        color: var(--ink) !important;
    }
    [data-testid="stSidebar"] input,
    [data-testid="stSidebar"] textarea,
    [data-testid="stSidebar"] [data-baseweb="select"] > div {
        color: var(--ink) !important;
        background-color: #242427 !important;
        border-color: #48484b !important;
    }
    [data-testid="stMetric"] {
        background: rgba(28, 28, 30, 0.82);
        border: 1px solid var(--border);
        border-radius: 6px;
        padding: 0.85rem 1rem;
    }
    [data-testid="stMetricLabel"] { color: var(--muted); }
    .eyebrow {
        color: var(--accent);
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
        font-size: 0.75rem;
        text-transform: uppercase;
    }
    .subtle { color: var(--muted) !important; }
    div.stButton > button[kind="primary"] {
        background: var(--accent);
        border-color: var(--accent);
        border-radius: 6px;
    }
    div.stButton > button[kind="primary"]:hover {
        background: #409cff;
        border-color: #409cff;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _model_picker(tier: str, provider: str, default_model: str) -> str:
    model_options = get_model_options(provider, tier)
    model_ids = [model_id for _, model_id in model_options]
    labels = {model_id: label for label, model_id in model_options}
    default_choice = default_model if default_model in model_ids else model_ids[0]
    selected = st.sidebar.selectbox(
        f"{tier.title()} model",
        model_ids,
        index=model_ids.index(default_choice),
        format_func=lambda model_id: labels[model_id],
        key=f"{tier}_model_{provider}",
    )
    if selected == "custom":
        custom_model = st.sidebar.text_input(
            f"Custom {tier} model ID",
            value=default_model if default_model not in model_ids else "",
            key=f"{tier}_custom_model_{provider}",
            placeholder="Enter the model ID served by your provider",
        ).strip()
        return custom_model
    return selected


def _render_sidebar() -> dict:
    config = DEFAULT_CONFIG
    st.sidebar.markdown("<span class='eyebrow'>Run configuration</span>", unsafe_allow_html=True)
    ticker_input = st.sidebar.text_input("Ticker", value="NVDA", max_chars=32)
    trade_date = st.sidebar.date_input("Analysis date", value=date.today(), max_value=date.today())

    provider_ids = list(MODEL_OPTIONS)
    provider = st.sidebar.selectbox(
        "LLM provider",
        provider_ids,
        index=provider_ids.index(config["llm_provider"])
        if config["llm_provider"] in provider_ids
        else 0,
        format_func=lambda provider_id: provider_id.replace("_", " ").title(),
    )
    quick_model = _model_picker("quick", provider, config["quick_think_llm"])
    deep_model = _model_picker("deep", provider, config["deep_think_llm"])

    analyst_types = filter_analysts_for_asset_type(list(AnalystType), detect_asset_type(ticker_input))
    available_analysts = [analyst.value for analyst in analyst_types]
    analysts = st.sidebar.multiselect(
        "Analyst team",
        available_analysts,
        default=available_analysts,
        format_func=lambda analyst: ANALYST_LABELS[analyst],
    )

    with st.sidebar.expander("Run options", expanded=False):
        max_debate_rounds = st.slider("Research debate rounds", 1, 5, config["max_debate_rounds"])
        max_risk_rounds = st.slider("Risk debate rounds", 1, 5, config["max_risk_discuss_rounds"])
        output_language = st.text_input("Report language", value=config["output_language"])
        backend_url = st.text_input(
            "Custom backend URL",
            value=config.get("backend_url") or "",
            placeholder="Only for compatible/custom endpoints",
        )

    key_env = get_api_key_env(provider)
    if key_env:
        st.sidebar.caption(f"Credentials are read from `{key_env}` in your environment or `.env` file.")
    else:
        st.sidebar.caption("Provider credentials are read from your environment or cloud credential chain.")
    st.sidebar.caption("API keys are not entered or stored in this interface.")

    run_clicked = st.sidebar.button("Run analysis", type="primary", use_container_width=True)
    return {
        "ticker": ticker_input,
        "trade_date": trade_date,
        "provider": provider,
        "quick_model": quick_model,
        "deep_model": deep_model,
        "analysts": analysts,
        "max_debate_rounds": max_debate_rounds,
        "max_risk_rounds": max_risk_rounds,
        "output_language": output_language,
        "backend_url": backend_url,
        "run_clicked": run_clicked,
    }


def _run_analysis(settings: dict) -> None:
    try:
        ticker = parse_ticker(settings["ticker"])
    except ValueError as exc:
        st.sidebar.error(str(exc))
        return

    if not settings["analysts"]:
        st.sidebar.error("Select at least one analyst.")
        return
    if not settings["quick_model"] or not settings["deep_model"]:
        st.sidebar.error("Enter a model ID for both model tiers.")
        return
    if not settings["output_language"].strip():
        st.sidebar.error("Report language cannot be empty.")
        return

    asset_type = detect_asset_type(ticker).value
    config = DEFAULT_CONFIG.copy()
    config.update(
        {
            "llm_provider": settings["provider"],
            "quick_think_llm": settings["quick_model"],
            "deep_think_llm": settings["deep_model"],
            "max_debate_rounds": settings["max_debate_rounds"],
            "max_risk_discuss_rounds": settings["max_risk_rounds"],
            "output_language": settings["output_language"].strip(),
            "backend_url": settings["backend_url"].strip() or None,
        }
    )
    st.session_state.pop("analysis_result", None)

    try:
        with st.status(f"Analyzing {ticker}...", expanded=True) as status:
            graph = TradingAgentsGraph(
                selected_analysts=settings["analysts"],
                config=config,
                debug=False,
            )
            final_state, decision = graph.propagate(
                ticker,
                settings["trade_date"].isoformat(),
                asset_type=asset_type,
            )
            report_path = graph.save_reports(final_state, ticker)
            report_html_path = report_path.with_name("complete_report.html")
            status.update(label=f"Analysis complete for {ticker}", state="complete", expanded=False)

        st.session_state["analysis_result"] = {
            "ticker": ticker,
            "trade_date": settings["trade_date"].isoformat(),
            "asset_type": asset_type,
            "decision": final_state.get("final_trade_decision") or decision,
            "rating": run_rating(final_state),
            "markdown": report_path.read_text(encoding="utf-8"),
            "html": report_html_path.read_text(encoding="utf-8")
            if report_html_path.exists()
            else None,
            "report_path": str(report_path),
        }
    except Exception as exc:
        st.error(f"The analysis could not be completed: {exc}")


def _render_result() -> None:
    result = st.session_state.get("analysis_result")
    if not result:
        st.markdown("### Ready when you are")
        st.markdown(
            "Set the run options in the sidebar to generate a multi-agent research report. "
            "The analysis is informational and does not place trades."
        )
        st.markdown(
            "<div class='subtle'>Provider credentials must be available in the process environment or a local <code>.env</code> file.</div>",
            unsafe_allow_html=True,
        )
        return

    st.markdown(f"<span class='eyebrow'>{result['asset_type']} analysis</span>", unsafe_allow_html=True)
    st.title(f"{result['ticker']} research")
    st.caption(f"Analysis date: {result['trade_date']}")
    metric, decision = st.columns([1, 3])
    metric.metric("Portfolio rating", result["rating"])
    with decision:
        st.markdown("**Portfolio decision**")
        st.markdown(str(result["decision"]))

    download_columns = st.columns(2)
    download_columns[0].download_button(
        "Download Markdown report",
        data=result["markdown"],
        file_name=f"{result['ticker']}_{result['trade_date']}_report.md",
        mime="text/markdown",
    )
    if result["html"]:
        download_columns[1].download_button(
            "Download HTML report",
            data=result["html"],
            file_name=f"{result['ticker']}_{result['trade_date']}_report.html",
            mime="text/html",
        )
    with st.expander("Complete analysis report", expanded=True):
        st.markdown(result["markdown"])
    st.caption(f"Saved report: {result['report_path']}")


st.markdown("<span class='eyebrow'>Multi-agent market research</span>", unsafe_allow_html=True)
st.title("TradingAgents")
st.markdown("Configure a research run, review the team’s decision, and download the report.")
st.divider()

run_settings = _render_sidebar()
if run_settings["run_clicked"]:
    _run_analysis(run_settings)
_render_result()