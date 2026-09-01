"""TradingAgents Web UI - Streamlit-based browser interface."""

import sys
import datetime
from pathlib import Path

import streamlit as st

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ANALYST_OPTIONS = {
    "Market Analyst": "market",
    "Sentiment Analyst": "social",
    "News Analyst": "news",
    "Fundamentals Analyst": "fundamentals",
}

CRYPTO_SUFFIXES = ("-USD", "-USDT", "-USDC", "-BTC", "-ETH")

PROVIDERS = [
    ("OpenAI", "openai"),
    ("Google", "google"),
    ("Anthropic", "anthropic"),
    ("xAI", "xai"),
    ("DeepSeek", "deepseek"),
    ("Qwen", "qwen"),
    ("GLM", "glm"),
    ("MiniMax", "minimax"),
    ("OpenRouter", "openrouter"),
    ("Azure OpenAI", "azure"),
    ("Ollama", "ollama"),
]

DEPTH_OPTIONS = {
    "Shallow (1 round)": 1,
    "Medium (3 rounds)": 3,
    "Deep (5 rounds)": 5,
}

OUTPUT_LANGUAGES = [
    "English", "Chinese", "Japanese", "Korean",
    "Hindi", "Spanish", "Portuguese", "French",
    "German", "Arabic", "Russian",
]

# Agent status labels
AGENT_TEAMS = {
    "Analyst Team": ["Market Analyst", "Sentiment Analyst", "News Analyst", "Fundamentals Analyst"],
    "Research Team": ["Bull Researcher", "Bear Researcher", "Research Manager"],
    "Trading Team": ["Trader"],
    "Risk Management": ["Aggressive Analyst", "Conservative Analyst", "Neutral Analyst"],
    "Portfolio Management": ["Portfolio Manager"],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def detect_asset_type(ticker: str) -> str:
    if ticker.upper().endswith(CRYPTO_SUFFIXES):
        return "crypto"
    return "stock"


def get_model_list(provider: str, mode: str) -> list[tuple[str, str]]:
    """Return model options for a provider/mode, falling back to custom-only."""
    provider = provider.lower()
    if provider in MODEL_OPTIONS and mode in MODEL_OPTIONS[provider]:
        return MODEL_OPTIONS[provider][mode]
    return [("Custom model ID", "custom")]


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="TradingAgents Web UI",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Sidebar - Configuration
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("📈 TradingAgents")
    st.caption("Multi-Agents LLM Financial Trading Framework")
    st.divider()

    # --- Ticker & Date ---
    st.subheader("1. Target")
    ticker = st.text_input("Ticker Symbol", value="SPY", help="e.g. SPY, NVDA, 0700.HK, BTC-USD")
    asset_type = detect_asset_type(ticker)
    if asset_type == "crypto":
        st.info(f"Detected: **crypto** asset")

    analysis_date = st.date_input(
        "Analysis Date",
        value=datetime.date.today(),
        max_value=datetime.date.today(),
    )
    date_str = analysis_date.strftime("%Y-%m-%d")

    # --- Output Language ---
    st.subheader("2. Language")
    output_language = st.selectbox("Report Language", OUTPUT_LANGUAGES, index=0)

    # --- Analysts ---
    st.subheader("3. Analysts")
    selected_analysts = []
    for display, key in ANALYST_OPTIONS.items():
        # Hide Fundamentals for crypto
        if asset_type == "crypto" and key == "fundamentals":
            continue
        if st.checkbox(display, value=True, key=f"analyst_{key}"):
            selected_analysts.append(key)

    if not selected_analysts:
        st.warning("Select at least one analyst.")

    # --- Research Depth ---
    st.subheader("4. Research Depth")
    depth_label = st.selectbox("Depth", list(DEPTH_OPTIONS.keys()), index=0)
    research_depth = DEPTH_OPTIONS[depth_label]

    # --- LLM Provider ---
    st.subheader("5. LLM Provider")
    provider_display = st.selectbox(
        "Provider",
        [p[0] for p in PROVIDERS],
        index=0,
    )
    provider_key = next(p[1] for p in PROVIDERS if p[0] == provider_display)

    # Model selection
    quick_models = get_model_list(provider_key, "quick")
    deep_models = get_model_list(provider_key, "deep")

    quick_model_names = [m[0] for m in quick_models]
    deep_model_names = [m[0] for m in deep_models]

    quick_choice = st.selectbox("Quick-Thinking Model", quick_model_names, index=0)
    deep_choice = st.selectbox("Deep-Thinking Model", deep_model_names, index=0)

    # Resolve model ID
    quick_model_id = next((v for n, v in quick_models if n == quick_choice), quick_choice)
    deep_model_id = next((v for n, v in deep_models if n == deep_choice), deep_choice)

    if quick_model_id == "custom":
        quick_model_id = st.text_input("Custom Quick Model ID", value="")
    if deep_model_id == "custom":
        deep_model_id = st.text_input("Custom Deep Model ID", value="")

    # --- Provider-specific options ---
    if provider_key == "openai":
        effort = st.selectbox("Reasoning Effort", ["medium", "high", "low"], index=0)
        config_effort = effort
        config_gemini = None
        config_anthropic = None
    elif provider_key == "google":
        thinking = st.selectbox("Thinking Mode", ["high", "minimal"], index=0)
        config_effort = None
        config_gemini = thinking
        config_anthropic = None
    elif provider_key == "anthropic":
        effort = st.selectbox("Effort Level", ["high", "medium", "low"], index=0)
        config_effort = None
        config_gemini = None
        config_anthropic = effort
    else:
        config_effort = None
        config_gemini = None
        config_anthropic = None

    st.divider()

    # --- Run button ---
    run_clicked = st.button(
        "🚀 Run Analysis",
        type="primary",
        use_container_width=True,
        disabled=not selected_analysts or (quick_model_id == "" or deep_model_id == ""),
    )


# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------

if "result" not in st.session_state:
    st.session_state.result = None
    st.session_state.final_state = None
    st.session_state.agent_statuses = {}
    st.session_state.report_sections = {}
    st.session_state.messages = []
    st.session_state.running = False


def reset_state():
    st.session_state.result = None
    st.session_state.final_state = None
    st.session_state.agent_statuses = {agent: "pending" for team in AGENT_TEAMS.values() for agent in team}
    st.session_state.report_sections = {}
    st.session_state.messages = []
    st.session_state.running = True


# Header
st.markdown("# 📈 TradingAgents Analysis")
st.caption("Agent workflow: Analyst Team → Research Team → Trader → Risk Management → Portfolio Manager")

if run_clicked:
    reset_state()

    # Lazy imports — only loaded when analysis starts, so initial page load is instant
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.graph.analyst_execution import (
        AnalystWallTimeTracker,
        build_analyst_execution_plan,
    )

    # Build config
    config = DEFAULT_CONFIG.copy()
    config["max_debate_rounds"] = research_depth
    config["max_risk_discuss_rounds"] = research_depth
    config["quick_think_llm"] = quick_model_id
    config["deep_think_llm"] = deep_model_id
    config["llm_provider"] = provider_key
    config["output_language"] = output_language
    config["google_thinking_level"] = config_gemini
    config["openai_reasoning_effort"] = config_effort
    config["anthropic_effort"] = config_anthropic

    # Progress containers
    status_container = st.empty()
    report_container = st.empty()
    message_log = st.empty()

    progress_bar = st.progress(0, text="Initializing...")

    try:
        # Init graph
        graph = TradingAgentsGraph(selected_analysts, config=config, debug=True)

        # Resolve instrument
        instrument_context = graph.resolve_instrument_context(ticker, asset_type)
        init_state = graph.propagator.create_initial_state(
            ticker, date_str, asset_type=asset_type, instrument_context=instrument_context,
        )
        args = graph.propagator.get_graph_args()

        # Analyst execution plan
        analyst_plan = build_analyst_execution_plan(selected_analysts, concurrency_limit=1)
        wall_tracker = AnalystWallTimeTracker(analyst_plan)

        # Stream the graph
        trace = []
        total_agents = sum(len(agents) for agents in AGENT_TEAMS.values())
        completed_agents = 0

        for chunk in graph.graph.stream(init_state, **args):
            trace.append(chunk)

            # Update agent statuses based on chunk
            for key in ["market_report", "sentiment_report", "news_report", "fundamentals_report"]:
                if chunk.get(key):
                    analyst_name = {
                        "market_report": "Market Analyst",
                        "sentiment_report": "Sentiment Analyst",
                        "news_report": "News Analyst",
                        "fundamentals_report": "Fundamentals Analyst",
                    }.get(key)
                    if analyst_name:
                        st.session_state.agent_statuses[analyst_name] = "completed"
                        st.session_state.report_sections[key] = chunk[key]

            if chunk.get("investment_debate_state"):
                debate = chunk["investment_debate_state"]
                if debate.get("judge_decision"):
                    for a in ["Bull Researcher", "Bear Researcher", "Research Manager"]:
                        st.session_state.agent_statuses[a] = "completed"
                    st.session_state.report_sections["investment_plan"] = debate["judge_decision"]

            if chunk.get("trader_investment_plan"):
                st.session_state.agent_statuses["Trader"] = "completed"
                st.session_state.report_sections["trader_investment_plan"] = chunk["trader_investment_plan"]

            if chunk.get("risk_debate_state"):
                risk = chunk["risk_debate_state"]
                if risk.get("judge_decision"):
                    for a in ["Aggressive Analyst", "Conservative Analyst", "Neutral Analyst", "Portfolio Manager"]:
                        st.session_state.agent_statuses[a] = "completed"
                    st.session_state.report_sections["final_trade_decision"] = risk["judge_decision"]

            # Update progress
            completed = sum(1 for s in st.session_state.agent_statuses.values() if s == "completed")
            progress = min(completed / total_agents, 1.0)
            progress_bar.progress(progress, text=f"Agents: {completed}/{total_agents}")

            # Update status display
            with status_container.container():
                cols = st.columns(len(AGENT_TEAMS))
                for i, (team, agents) in enumerate(AGENT_TEAMS.items()):
                    with cols[i]:
                        st.markdown(f"**{team}**")
                        for agent in agents:
                            status = st.session_state.agent_statuses.get(agent, "pending")
                            icon = {"pending": "⏳", "in_progress": "🔄", "completed": "✅"}.get(status, "⏳")
                            st.caption(f"{icon} {agent}")

            # Update report
            if st.session_state.report_sections:
                with report_container.container():
                    st.divider()
                    st.subheader("📊 Analysis Reports")
                    tabs = st.tabs([
                        "Market", "Sentiment", "News", "Fundamentals",
                        "Research", "Trading", "Risk & Decision"
                    ])
                    with tabs[0]:
                        st.markdown(st.session_state.report_sections.get("market_report", "*Pending...*"))
                    with tabs[1]:
                        st.markdown(st.session_state.report_sections.get("sentiment_report", "*Pending...*"))
                    with tabs[2]:
                        st.markdown(st.session_state.report_sections.get("news_report", "*Pending...*"))
                    with tabs[3]:
                        st.markdown(st.session_state.report_sections.get("fundamentals_report", "*Pending...*"))
                    with tabs[4]:
                        st.markdown(st.session_state.report_sections.get("investment_plan", "*Pending...*"))
                    with tabs[5]:
                        st.markdown(st.session_state.report_sections.get("trader_investment_plan", "*Pending...*"))
                    with tabs[6]:
                        st.markdown(st.session_state.report_sections.get("final_trade_decision", "*Pending...*"))

        # Merge final state
        final_state = {}
        for chunk in trace:
            final_state.update(chunk)

        decision = graph.process_signal(final_state["final_trade_decision"])
        st.session_state.final_state = final_state
        st.session_state.result = decision

        progress_bar.progress(1.0, text="✅ Analysis complete!")

        # Final display
        st.success(f"**Decision: {decision.upper()}**")

        # Save report option
        st.divider()
        if st.button("💾 Save Report to Disk"):
            from cli.main import save_report_to_disk
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = Path.cwd() / "reports" / f"{ticker}_{timestamp}"
            report_file = save_report_to_disk(final_state, ticker, save_path)
            st.success(f"Report saved to: `{save_path}`")

    except Exception as e:
        st.error(f"Analysis failed: {e}")
        st.exception(e)
    finally:
        st.session_state.running = False

elif st.session_state.final_state:
    # Show previous result
    final_state = st.session_state.final_state
    decision = st.session_state.result

    if decision:
        st.success(f"**Last Decision: {decision.upper()}**")

    st.divider()
    st.subheader("📊 Analysis Reports")
    tabs = st.tabs([
        "Market", "Sentiment", "News", "Fundamentals",
        "Research", "Trading", "Risk & Decision"
    ])
    with tabs[0]:
        st.markdown(final_state.get("market_report", "*No data*"))
    with tabs[1]:
        st.markdown(final_state.get("sentiment_report", "*No data*"))
    with tabs[2]:
        st.markdown(final_state.get("news_report", "*No data*"))
    with tabs[3]:
        st.markdown(final_state.get("fundamentals_report", "*No data*"))
    with tabs[4]:
        debate = final_state.get("investment_debate_state", {})
        st.markdown(debate.get("judge_decision", "*No data*"))
    with tabs[5]:
        st.markdown(final_state.get("trader_investment_plan", "*No data*"))
    with tabs[6]:
        risk = final_state.get("risk_debate_state", {})
        st.markdown(risk.get("judge_decision", "*No data*"))

    # Save button
    st.divider()
    if st.button("💾 Save Report to Disk"):
        from cli.main import save_report_to_disk
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = Path.cwd() / "reports" / f"{ticker}_{timestamp}"
        report_file = save_report_to_disk(final_state, ticker, save_path)
        st.success(f"Report saved to: `{save_path}`")

else:
    # Welcome screen
    st.markdown("""
    ### Welcome to TradingAgents Web UI

    Configure your analysis in the sidebar and click **Run Analysis** to start.

    **Workflow:**
    1. 📊 **Analyst Team** - Market, Sentiment, News, Fundamentals analysis
    2. 🔬 **Research Team** - Bull vs Bear debate moderated by Research Manager
    3. 💹 **Trader** - Creates trading plan
    4. ⚖️ **Risk Management** - Aggressive vs Conservative vs Neutral debate
    5. 🎯 **Portfolio Manager** - Final decision

    ---
    *Built by [Tauric Research](https://github.com/TauricResearch)*
    """)
