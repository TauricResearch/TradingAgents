import datetime
import os
import sys
import time
from pathlib import Path

import streamlit as st

# Add parent directory to sys.path if needed
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli.models import AnalystType, AssetType
from cli.stats_handler import StatsCallbackHandler
from cli.utils import (
    ANALYST_ORDER,
    CRYPTO_SUFFIXES,
    _llm_provider_table,
    detect_asset_type,
    filter_analysts_for_asset_type,
    get_api_key_env,
    get_model_options,
    normalize_ticker_symbol,
    provider_default_url,
    resolve_backend_url,
)
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.analyst_execution import (
    AnalystWallTimeTracker,
    build_analyst_execution_plan,
    get_initial_analyst_node,
    sync_analyst_tracker_from_chunk,
)
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.reporting import write_report_tree


# Page config
st.set_page_config(
    page_title="TradingAgents — Multi-Agent LLM Trading Framework",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for polished trading dashboard appearance
st.markdown(
    """
    <style>
    .main .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }
    .stMetric {
        background-color: rgba(28, 131, 225, 0.05);
        border: 1px solid rgba(28, 131, 225, 0.2);
        padding: 10px;
        border-radius: 8px;
    }
    .status-card {
        padding: 12px;
        border-radius: 8px;
        border: 1px solid #e0e0e0;
        margin-bottom: 10px;
    }
    .status-pending { background-color: #fffbe6; border-color: #ffe58f; }
    .status-in_progress { background-color: #e6f7ff; border-color: #91d5ff; }
    .status-completed { background-color: #f6ffed; border-color: #b7eb8f; }
    .status-error { background-color: #fff2f0; border-color: #ffccc7; }
    .badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.8rem;
        font-weight: bold;
    }
    .badge-pending { background-color: #faad14; color: white; }
    .badge-in_progress { background-color: #1890ff; color: white; }
    .badge-completed { background-color: #52c41a; color: white; }
    .badge-error { background-color: #ff4d4f; color: white; }
    </style>
    """,
    unsafe_allow_html=True,
)


def init_session_state():
    """Initialize Streamlit session state keys."""
    if "is_running" not in st.session_state:
        st.session_state.is_running = False
    if "analysis_complete" not in st.session_state:
        st.session_state.analysis_complete = False
    if "messages_log" not in st.session_state:
        st.session_state.messages_log = []
    if "tool_calls_log" not in st.session_state:
        st.session_state.tool_calls_log = []
    if "report_sections" not in st.session_state:
        st.session_state.report_sections = {}
    if "agent_status" not in st.session_state:
        st.session_state.agent_status = {}
    if "final_state" not in st.session_state:
        st.session_state.final_state = {}
    if "stats" not in st.session_state:
        st.session_state.stats = {
            "llm_calls": 0,
            "tool_calls": 0,
            "tokens_in": 0,
            "tokens_out": 0,
            "elapsed": "00:00",
        }


init_session_state()

# Fixed teams mapping for UI agent status cards
FIXED_AGENTS = {
    "Analyst Team": ["Market Analyst", "Sentiment Analyst", "News Analyst", "Fundamentals Analyst"],
    "Research Team": ["Bull Researcher", "Bear Researcher", "Research Manager"],
    "Trading Team": ["Trader"],
    "Risk Management": ["Aggressive Analyst", "Neutral Analyst", "Conservative Analyst"],
    "Portfolio Management": ["Portfolio Manager"],
}

ANALYST_AGENT_NAMES = {
    "market": "Market Analyst",
    "social": "Sentiment Analyst",
    "news": "News Analyst",
    "fundamentals": "Fundamentals Analyst",
}


# --- SIDEBAR CONFIGURATION ---
with st.sidebar:
    st.title(" TradingAgents UI")
    st.caption("Multi-Agent LLM Financial Trading Framework")
    st.markdown("---")

    st.subheader("1. Asset & Target")
    ticker_input = st.text_input(
        "Ticker Symbol",
        value="SPY",
        help="Target market symbol (e.g., SPY, AAPL, 0700.HK, BTC-USD)",
    )
    ticker = normalize_ticker_symbol(ticker_input) if ticker_input.strip() else "SPY"
    asset_type = detect_asset_type(ticker)

    if asset_type == AssetType.CRYPTO:
        st.info(f"Asset Type Detected: **Crypto** ({ticker})")
    else:
        st.info(f"Asset Type Detected: **Stock/Equity** ({ticker})")

    analysis_date = st.date_input(
        "Analysis Date",
        value=datetime.date.today(),
        max_value=datetime.date.today(),
    ).strftime("%Y-%m-%d")

    output_language = st.selectbox(
        "Output Language",
        options=[
            "English",
            "Chinese",
            "Japanese",
            "Korean",
            "Hindi",
            "Spanish",
            "Portuguese",
            "French",
            "German",
            "Russian",
        ],
        index=0,
    )

    st.markdown("---")
    st.subheader("2. Analysts Team")

    available_analyst_keys = filter_analysts_for_asset_type(
        [v for _, v in ANALYST_ORDER], asset_type
    )

    selected_analyst_keys = []
    for display_name, key in ANALYST_ORDER:
        if key in available_analyst_keys:
            default_checked = True
            checked = st.checkbox(display_name, value=default_checked, key=f"chk_{key}")
            if checked:
                selected_analyst_keys.append(key.value if hasattr(key, "value") else str(key))

    if not selected_analyst_keys:
        st.warning("Please select at least one analyst.")

    st.markdown("---")
    st.subheader("3. Model & Provider Settings")

    providers_table = _llm_provider_table()
    provider_options = [p[0] for p in providers_table]
    provider_key_map = {p[0]: p[1] for p in providers_table}

    default_prov_idx = 0
    selected_prov_display = st.selectbox("LLM Provider", options=provider_options, index=default_prov_idx)
    selected_provider_key = provider_key_map[selected_prov_display]

    # Handle regional / custom endpoint specifics
    backend_url = provider_default_url(selected_provider_key)
    if selected_provider_key == "qwen":
        qwen_reg = st.radio(
            "Qwen Region",
            ["International (dashscope-intl)", "China (dashscope)"],
            index=0,
        )
        if "China" in qwen_reg:
            selected_provider_key = "qwen-cn"
            backend_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    elif selected_provider_key == "glm":
        glm_reg = st.radio("GLM Region", ["Z.AI (International)", "BigModel (China)"], index=0)
        if "China" in glm_reg:
            selected_provider_key = "glm-cn"
            backend_url = "https://open.bigmodel.cn/api/paas/v4/"
    elif selected_provider_key == "minimax":
        mm_reg = st.radio("MiniMax Region", ["Global (api.minimax.io)", "China (api.minimaxi.com)"], index=0)
        if "China" in mm_reg:
            selected_provider_key = "minimax-cn"
            backend_url = "https://api.minimaxi.com/v1"
    elif selected_provider_key == "ollama":
        backend_url = st.text_input("Ollama Base URL", value=backend_url or "http://localhost:11434/v1")
    elif selected_provider_key == "openai_compatible":
        backend_url = st.text_input("OpenAI-Compatible Base URL", value="http://localhost:8000/v1")

    # API key check & prompt
    env_key_var = get_api_key_env(selected_provider_key)
    if env_key_var:
        existing_key = os.environ.get(env_key_var, "")
        user_key = st.text_input(
            f"API Key ({env_key_var})",
            value=existing_key,
            type="password",
            help="Enter or override API Key for the selected provider.",
        )
        if user_key and user_key != existing_key:
            os.environ[env_key_var] = user_key

    # Model catalog selection
    shallow_options = [opt[0] for opt in get_model_options(selected_provider_key, "quick")]
    deep_options = [opt[0] for opt in get_model_options(selected_provider_key, "deep")]

    shallow_val_map = {opt[0]: opt[1] for opt in get_model_options(selected_provider_key, "quick")}
    deep_val_map = {opt[0]: opt[1] for opt in get_model_options(selected_provider_key, "deep")}

    shallow_choice = st.selectbox("Quick-Thinking Model", options=shallow_options, index=0)
    shallow_model = shallow_val_map.get(shallow_choice, "gpt-5.6-luna")
    if shallow_model == "custom":
        shallow_model = st.text_input("Custom Quick Model ID", value="gpt-5.6-luna")

    deep_choice = st.selectbox("Deep-Thinking Model", options=deep_options, index=0)
    deep_model = deep_val_map.get(deep_choice, "gpt-5.6")
    if deep_model == "custom":
        deep_model = st.text_input("Custom Deep Model ID", value="gpt-5.6")

    # Provider reasoning/thinking knobs
    google_thinking_level = None
    openai_reasoning_effort = None
    anthropic_effort = None

    if selected_provider_key in ("openai", "openai_compatible"):
        openai_reasoning_effort = st.select_slider(
            "OpenAI Reasoning Effort", options=["low", "medium", "high"], value="medium"
        )
    elif selected_provider_key == "google":
        google_thinking_level = st.radio("Gemini Thinking Mode", ["high", "minimal"], index=0)
    elif selected_provider_key == "anthropic":
        anthropic_effort = st.select_slider("Claude Effort", options=["low", "medium", "high"], value="high")

    st.markdown("---")
    st.subheader("4. Execution Controls")

    research_depth = st.select_slider(
        "Research Depth (Debate Rounds)",
        options=[1, 2, 3, 4, 5],
        value=3,
        help="Higher values trigger more debate rounds between Bull/Bear researchers and Risk Management analysts.",
    )

    checkpoint_enabled = st.checkbox("Enable Checkpoint Resume", value=False)

    start_btn = st.button(
        "🚀 Start Trading Analysis",
        type="primary",
        disabled=st.session_state.is_running or not selected_analyst_keys,
        use_container_width=True,
    )


# --- MAIN INTERFACE CONTENT ---
st.title("📈 TradingAgents Dashboard")

tab_live, tab_report, tab_memory = st.tabs(
    ["⚡ Live Analysis Hub", "📊 Report & Decision Explorer", "📁 Memory & History Browser"]
)


# Helper function to render status badge
def render_status_pill(status: str) -> str:
    status_clean = status.lower()
    badges = {
        "pending": "⏳ Pending",
        "in_progress": "🔄 In Progress",
        "completed": "✅ Completed",
        "error": "❌ Error",
    }
    badge_text = badges.get(status_clean, status)
    badge_class = f"badge-{status_clean}" if status_clean in badges else "badge-pending"
    return f'<span class="badge {badge_class}">{badge_text}</span>'


# ==========================================
# TAB 1: LIVE ANALYSIS HUB
# ==========================================
with tab_live:
    # Stats Header Metrics
    st.subheader("Execution Real-Time Status")
    col1, col2, col3, col4, col5 = st.columns(5)
    metric_llm = col1.metric("LLM Calls", st.session_state.stats["llm_calls"])
    metric_tools = col2.metric("Tool Calls", st.session_state.stats["tool_calls"])
    metric_tin = col3.metric("Tokens In", f"{st.session_state.stats['tokens_in']:,}")
    metric_tout = col4.metric("Tokens Out", f"{st.session_state.stats['tokens_out']:,}")
    metric_time = col5.metric("Elapsed Time", st.session_state.stats["elapsed"])

    st.markdown("---")

    col_left, col_right = st.columns([1, 2])

    with col_left:
        st.subheader("👥 Agent Teams & Progress")
        status_container = st.container()

        with status_container:
            for team_name, agents in FIXED_AGENTS.items():
                active_agents_in_team = [
                    a
                    for a in agents
                    if team_name != "Analyst Team"
                    or any(
                        ANALYST_AGENT_NAMES.get(k) == a for k in selected_analyst_keys
                    )
                ]
                if not active_agents_in_team:
                    continue

                st.markdown(f"**{team_name}**")
                for agent_name in active_agents_in_team:
                    status = st.session_state.agent_status.get(agent_name, "pending")
                    pill_html = render_status_pill(status)
                    st.markdown(
                        f"<div class='status-card status-{status}'>"
                        f"<strong>{agent_name}</strong>: {pill_html}"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

    with col_right:
        st.subheader("💬 Live Thought & Tool Execution Stream")
        messages_expander = st.expander("Show Detailed Execution Log", expanded=True)
        log_container = messages_expander.container(height=350)

        st.subheader("📄 Active Section View")
        active_report_container = st.container(height=350)


# Execution logic when Start button is pressed
if start_btn:
    st.session_state.is_running = True
    st.session_state.analysis_complete = False
    st.session_state.messages_log.clear()
    st.session_state.tool_calls_log.clear()
    st.session_state.report_sections.clear()
    st.session_state.final_state.clear()

    # Initialize agent status
    st.session_state.agent_status = {}
    for key in selected_analyst_keys:
        if key in ANALYST_AGENT_NAMES:
            st.session_state.agent_status[ANALYST_AGENT_NAMES[key]] = "pending"
    for team_agents in FIXED_AGENTS.values():
        for agent in team_agents:
            if agent not in st.session_state.agent_status and (
                agent not in ANALYST_AGENT_NAMES.values()
            ):
                st.session_state.agent_status[agent] = "pending"

    # Set initial active analyst
    execution_plan = build_analyst_execution_plan(selected_analyst_keys)
    wall_tracker = AnalystWallTimeTracker(execution_plan)
    first_analyst = get_initial_analyst_node(execution_plan)
    if first_analyst in st.session_state.agent_status:
        st.session_state.agent_status[first_analyst] = "in_progress"

    # Build graph configuration
    config = DEFAULT_CONFIG.copy()
    config["max_debate_rounds"] = research_depth
    config["max_risk_discuss_rounds"] = research_depth
    config["quick_think_llm"] = shallow_model
    config["deep_think_llm"] = deep_model
    config["backend_url"] = backend_url
    config["llm_provider"] = selected_provider_key
    config["google_thinking_level"] = google_thinking_level
    config["openai_reasoning_effort"] = openai_reasoning_effort
    config["anthropic_effort"] = anthropic_effort
    config["output_language"] = output_language
    config["checkpoint_enabled"] = checkpoint_enabled

    stats_handler = StatsCallbackHandler()

    graph = TradingAgentsGraph(
        selected_analyst_keys,
        config=config,
        debug=True,
        callbacks=[stats_handler],
    )

    instrument_context = graph.resolve_instrument_context(ticker, asset_type.value)
    init_state = graph.propagator.create_initial_state(
        ticker,
        analysis_date,
        asset_type=asset_type.value,
        instrument_context=instrument_context,
    )
    graph_args = graph.propagator.get_graph_args(callbacks=[stats_handler])

    checkpoint_tid = graph.begin_checkpoint(ticker, analysis_date, asset_type.value)
    if checkpoint_tid is not None:
        graph_args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = checkpoint_tid

    start_time = time.time()
    trace = []

    try:
        with st.spinner(f"Analyzing {ticker} on {analysis_date}..."):
            for chunk in graph.graph.stream(graph.checkpoint_input(init_state), **graph_args):
                trace.append(chunk)

                # Update callback stats
                curr_stats = stats_handler.get_stats()
                elapsed_sec = int(time.time() - start_time)
                elapsed_str = f"{elapsed_sec // 60:02d}:{elapsed_sec % 60:02d}"

                st.session_state.stats = {
                    "llm_calls": curr_stats["llm_calls"],
                    "tool_calls": curr_stats["tool_calls"],
                    "tokens_in": curr_stats["tokens_in"],
                    "tokens_out": curr_stats["tokens_out"],
                    "elapsed": elapsed_str,
                }

                # Update analyst statuses
                sync_analyst_tracker_from_chunk(wall_tracker, chunk)
                for a_key, a_name in ANALYST_AGENT_NAMES.items():
                    if a_key in selected_analyst_keys:
                        rep_key = f"{a_key}_report"
                        if chunk.get(rep_key):
                            st.session_state.report_sections[rep_key] = chunk[rep_key]
                            st.session_state.agent_status[a_name] = "completed"

                # Research team state
                if chunk.get("investment_debate_state"):
                    deb = chunk["investment_debate_state"]
                    if deb.get("bull_history"):
                        st.session_state.agent_status["Bull Researcher"] = "in_progress"
                        st.session_state.report_sections["bull_research"] = deb["bull_history"]
                    if deb.get("bear_history"):
                        st.session_state.agent_status["Bear Researcher"] = "in_progress"
                        st.session_state.report_sections["bear_research"] = deb["bear_history"]
                    if deb.get("judge_decision"):
                        st.session_state.agent_status["Bull Researcher"] = "completed"
                        st.session_state.agent_status["Bear Researcher"] = "completed"
                        st.session_state.agent_status["Research Manager"] = "completed"
                        st.session_state.agent_status["Trader"] = "in_progress"
                        st.session_state.report_sections["investment_plan"] = deb["judge_decision"]

                # Trading team state
                if chunk.get("trader_investment_plan"):
                    st.session_state.report_sections["trader_investment_plan"] = chunk[
                        "trader_investment_plan"
                    ]
                    st.session_state.agent_status["Trader"] = "completed"
                    st.session_state.agent_status["Aggressive Analyst"] = "in_progress"

                # Risk management state
                if chunk.get("risk_debate_state"):
                    risk = chunk["risk_debate_state"]
                    if risk.get("aggressive_history"):
                        st.session_state.report_sections["agg_risk"] = risk["aggressive_history"]
                        st.session_state.agent_status["Aggressive Analyst"] = "completed"
                        st.session_state.agent_status["Conservative Analyst"] = "in_progress"
                    if risk.get("conservative_history"):
                        st.session_state.report_sections["con_risk"] = risk["conservative_history"]
                        st.session_state.agent_status["Conservative Analyst"] = "completed"
                        st.session_state.agent_status["Neutral Analyst"] = "in_progress"
                    if risk.get("neutral_history"):
                        st.session_state.report_sections["neu_risk"] = risk["neutral_history"]
                        st.session_state.agent_status["Neutral Analyst"] = "completed"
                        st.session_state.agent_status["Portfolio Manager"] = "in_progress"
                    if risk.get("judge_decision"):
                        st.session_state.report_sections["final_trade_decision"] = risk["judge_decision"]
                        st.session_state.agent_status["Portfolio Manager"] = "completed"

                # Extract messages for live log
                for msg in chunk.get("messages", []):
                    msg_content = getattr(msg, "content", None)
                    if msg_content:
                        st.session_state.messages_log.append(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg_content}")

                st.rerun()

        graph.clear_checkpoint_on_success(ticker, analysis_date, asset_type.value)
    finally:
        graph.end_checkpoint()

    # Merge final state
    final_state = {}
    for c in trace:
        final_state.update(c)
    st.session_state.final_state = final_state

    # Save report to disk
    try:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = Path.cwd() / "reports" / f"{ticker}_{timestamp}"
        write_report_tree(final_state, ticker, save_path)
    except Exception as e:
        st.error(f"Error auto-saving report: {e}")

    for agent in st.session_state.agent_status:
        st.session_state.agent_status[agent] = "completed"

    st.session_state.is_running = False
    st.session_state.analysis_complete = True
    st.success("✅ Analysis Complete! Switch to the 'Report & Decision Explorer' tab to view the full report.")
    st.rerun()


# Render live log & active report content
with log_container:
    if st.session_state.messages_log:
        for item in reversed(st.session_state.messages_log[-15:]):
            st.text(item[:300])
    else:
        st.info("Log stream ready. Start analysis to view live messages.")

with active_report_container:
    if st.session_state.report_sections:
        last_sec_key = list(st.session_state.report_sections.keys())[-1]
        last_sec_content = st.session_state.report_sections[last_sec_key]
        st.markdown(f"#### Active Section: `{last_sec_key}`")
        st.markdown(last_sec_content)
    else:
        st.info("No active report section rendered yet.")


# ==========================================
# TAB 2: REPORT & DECISION EXPLORER
# ==========================================
with tab_report:
    st.subheader("📊 Complete Analysis & Decision Breakdown")

    final_state = st.session_state.final_state
    if not final_state and not st.session_state.report_sections:
        st.info("Run an analysis in the 'Live Analysis Hub' tab to view structured reports here.")
    else:
        # Build consolidated markdown report string
        full_md_parts = [f"# TradingAgents Decision Report: {ticker}\n**Date**: {analysis_date}\n\n"]

        # I. Analyst Team Reports
        with st.expander("I. Analyst Team Reports", expanded=True):
            analyst_found = False
            for a_key, a_title in [
                ("market_report", "Market Analysis"),
                ("sentiment_report", "Social Sentiment Analysis"),
                ("news_report", "News Analysis"),
                ("fundamentals_report", "Fundamentals Analysis"),
            ]:
                content = final_state.get(a_key) or st.session_state.report_sections.get(a_key)
                if content:
                    analyst_found = True
                    st.markdown(f"### {a_title}")
                    st.markdown(content)
                    full_md_parts.append(f"## {a_title}\n{content}\n\n")
            if not analyst_found:
                st.caption("No analyst reports generated.")

        # II. Research Team Decision
        with st.expander("II. Research Team Decision & Debates", expanded=True):
            debate = final_state.get("investment_debate_state", {})
            if debate.get("bull_history"):
                st.markdown("### Bull Researcher Analysis")
                st.markdown(debate["bull_history"])
                full_md_parts.append(f"## Bull Researcher Analysis\n{debate['bull_history']}\n\n")
            if debate.get("bear_history"):
                st.markdown("### Bear Researcher Analysis")
                st.markdown(debate["bear_history"])
                full_md_parts.append(f"## Bear Researcher Analysis\n{debate['bear_history']}\n\n")
            if debate.get("judge_decision"):
                st.markdown("### Research Manager Decision")
                st.markdown(debate["judge_decision"])
                full_md_parts.append(f"## Research Manager Decision\n{debate['judge_decision']}\n\n")

        # III. Trading Team
        with st.expander("III. Trading Team Execution Strategy", expanded=True):
            trader_plan = final_state.get("trader_investment_plan") or st.session_state.report_sections.get(
                "trader_investment_plan"
            )
            if trader_plan:
                st.markdown(trader_plan)
                full_md_parts.append(f"## Trading Strategy\n{trader_plan}\n\n")

        # IV & V. Risk Management & Portfolio Manager
        with st.expander("IV & V. Risk Management & Final Decision", expanded=True):
            risk = final_state.get("risk_debate_state", {})
            if risk.get("aggressive_history"):
                st.markdown("### Aggressive Risk Analyst")
                st.markdown(risk["aggressive_history"])
            if risk.get("conservative_history"):
                st.markdown("### Conservative Risk Analyst")
                st.markdown(risk["conservative_history"])
            if risk.get("neutral_history"):
                st.markdown("### Neutral Risk Analyst")
                st.markdown(risk["neutral_history"])
            if risk.get("judge_decision"):
                st.markdown("### 🏆 Portfolio Manager Final Decision")
                st.success(risk["judge_decision"])
                full_md_parts.append(f"## Final Portfolio Manager Decision\n{risk['judge_decision']}\n\n")

        consolidated_report_str = "\n".join(full_md_parts)
        st.download_button(
            "📥 Download Full Report (.md)",
            data=consolidated_report_str,
            file_name=f"TradingAgents_{ticker}_{analysis_date}.md",
            mime="text/markdown",
            use_container_width=True,
        )


# ==========================================
# TAB 3: MEMORY & HISTORY BROWSER
# ==========================================
with tab_memory:
    st.subheader("📁 Saved Reports & Decision Memory")

    sub_tab1, sub_tab2 = st.tabs(["Saved Local Reports", "Persistent Decision Log Memory"])

    with sub_tab1:
        st.markdown("#### Reports Directory (`./reports` / `./results`)")
        reports_dir = Path.cwd() / "reports"
        results_dir = Path.cwd() / "results"

        found_files = []
        for p in [reports_dir, results_dir]:
            if p.exists():
                found_files.extend(list(p.glob("**/*.md")))

        if found_files:
            file_map = {f"{f.parent.name}/{f.name}": f for f in found_files}
            selected_file_name = st.selectbox("Select saved report to view:", options=list(file_map.keys()))
            if selected_file_name:
                selected_file_path = file_map[selected_file_name]
                with open(selected_file_path, encoding="utf-8") as rf:
                    content = rf.read()
                st.markdown(content)
        else:
            st.info("No saved report files found in `./reports` or `./results`.")

    with sub_tab2:
        st.markdown("#### Trading Decision Memory (`~/.tradingagents/memory/trading_memory.md`)")
        memory_path = Path.home() / ".tradingagents" / "memory" / "trading_memory.md"
        env_mem_path = os.environ.get("TRADINGAGENTS_MEMORY_LOG_PATH")
        if env_mem_path:
            memory_path = Path(env_mem_path)

        if memory_path.exists():
            with open(memory_path, encoding="utf-8") as mf:
                mem_text = mf.read()
            st.markdown(mem_text)
        else:
            st.info(f"Decision memory log not created yet at `{memory_path}`.")
