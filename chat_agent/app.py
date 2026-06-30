"""TradingAgents Chat Agent — Streamlit web app.

A conversational interface where users enter a stock ticker and receive
a full multi-agent trading analysis report.
"""

import datetime
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

CRYPTO_SUFFIXES = ("-USD", "-USDT", "-USDC", "-BTC", "-ETH")


def detect_asset_type(ticker: str) -> str:
    if ticker.upper().endswith(CRYPTO_SUFFIXES):
        return "crypto"
    return "stock"


def format_report(final_state: dict, ticker: str) -> str:
    """Build a markdown report from the final graph state."""
    sections = []
    sections.append(f"# Trading Analysis Report: {ticker}")
    sections.append(
        f"*Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"
    )

    analyst_parts = []
    for key, label in [
        ("market_report", "Market Analyst"),
        ("sentiment_report", "Sentiment Analyst"),
        ("news_report", "News Analyst"),
        ("fundamentals_report", "Fundamentals Analyst"),
    ]:
        if final_state.get(key):
            analyst_parts.append(f"### {label}\n{final_state[key]}")
    if analyst_parts:
        sections.append("## I. Analyst Team Reports\n\n" + "\n\n".join(analyst_parts))

    if final_state.get("investment_debate_state"):
        debate = final_state["investment_debate_state"]
        research_parts = []
        if debate.get("bull_history"):
            research_parts.append(f"### Bull Researcher\n{debate['bull_history']}")
        if debate.get("bear_history"):
            research_parts.append(f"### Bear Researcher\n{debate['bear_history']}")
        if debate.get("judge_decision"):
            research_parts.append(
                f"### Research Manager\n{debate['judge_decision']}"
            )
        if research_parts:
            sections.append(
                "## II. Research Team Decision\n\n" + "\n\n".join(research_parts)
            )

    if final_state.get("investment_plan"):
        sections.append(
            f"## III. Investment Plan\n\n{final_state['investment_plan']}"
        )

    if final_state.get("trader_investment_plan"):
        sections.append(
            f"## IV. Trading Team Plan\n\n### Trader\n{final_state['trader_investment_plan']}"
        )

    if final_state.get("risk_debate_state"):
        risk = final_state["risk_debate_state"]
        risk_parts = []
        if risk.get("aggressive_history"):
            risk_parts.append(
                f"### Aggressive Analyst\n{risk['aggressive_history']}"
            )
        if risk.get("conservative_history"):
            risk_parts.append(
                f"### Conservative Analyst\n{risk['conservative_history']}"
            )
        if risk.get("neutral_history"):
            risk_parts.append(f"### Neutral Analyst\n{risk['neutral_history']}")
        if risk_parts:
            sections.append(
                "## V. Risk Management Team\n\n" + "\n\n".join(risk_parts)
            )
        if risk.get("judge_decision"):
            sections.append(
                f"## VI. Portfolio Manager Decision\n\n{risk['judge_decision']}"
            )

    if final_state.get("final_trade_decision"):
        sections.append(
            f"## Final Decision\n\n{final_state['final_trade_decision']}"
        )

    return "\n\n".join(sections)


def run_analysis(ticker: str, trade_date: str, config: dict) -> dict:
    """Run the TradingAgents pipeline and return the final state."""
    asset_type = detect_asset_type(ticker)

    analysts = ["market", "social", "news", "fundamentals"]
    if asset_type == "crypto":
        analysts = [a for a in analysts if a != "fundamentals"]

    graph = TradingAgentsGraph(
        selected_analysts=analysts,
        config=config,
        debug=False,
    )
    final_state, decision = graph.propagate(ticker, trade_date, asset_type=asset_type)
    return final_state, decision


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="TradingAgents Chat",
    page_icon="📈",
    layout="wide",
)

st.title("📈 TradingAgents Chat")
st.caption(
    "Enter a stock ticker to get a full AI-powered trading analysis report."
)

# Sidebar: configuration
with st.sidebar:
    st.header("Configuration")

    llm_provider = st.selectbox(
        "LLM Provider",
        ["openai", "anthropic", "google", "deepseek", "groq"],
        index=0,
    )

    provider_models = {
        "openai": ("gpt-5.5", "gpt-5.4-mini"),
        "anthropic": ("claude-sonnet-4-6", "claude-haiku-4-5-20251001"),
        "google": ("gemini-2.5-pro", "gemini-2.5-flash"),
        "deepseek": ("deepseek-chat", "deepseek-chat"),
        "groq": ("llama-3.3-70b-versatile", "llama-3.1-8b-instant"),
    }
    default_deep, default_quick = provider_models.get(
        llm_provider, ("gpt-5.5", "gpt-5.4-mini")
    )

    deep_model = st.text_input("Deep thinking model", value=default_deep)
    quick_model = st.text_input("Quick thinking model", value=default_quick)
    debate_rounds = st.slider("Debate rounds", 1, 5, 1)

    api_key_label = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "google": "GOOGLE_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "groq": "GROQ_API_KEY",
    }.get(llm_provider, "OPENAI_API_KEY")

    api_key = st.text_input(
        f"{api_key_label}",
        type="password",
        help="Set your API key here. It is stored only in your session.",
    )
    if api_key:
        st.session_state["api_key"] = api_key

    st.divider()
    st.markdown(
        "**Note:** Analysis takes 2-5 minutes per ticker depending on "
        "model speed and debate rounds."
    )

# Chat history
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "Welcome! I can analyze any stock or crypto for you.\n\n"
                "Just type a **ticker symbol** (e.g. `NVDA`, `AAPL`, `BTC-USD`) "
                "and I'll run a full multi-agent analysis including:\n"
                "- Market & technical analysis\n"
                "- Sentiment analysis\n"
                "- News analysis\n"
                "- Fundamentals analysis\n"
                "- Bull vs Bear debate\n"
                "- Risk assessment\n"
                "- Final portfolio decision\n\n"
                "You can optionally include a date like `NVDA 2026-06-25`."
            ),
        }
    ]

if "running" not in st.session_state:
    st.session_state.running = False

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

user_input = st.chat_input(
    "Enter a ticker (e.g. NVDA, AAPL, BTC-USD)",
    disabled=st.session_state.running,
)

if user_input and not st.session_state.running:
    parts = user_input.strip().split()
    ticker = parts[0].upper()
    trade_date = parts[1] if len(parts) > 1 else datetime.date.today().strftime("%Y-%m-%d")

    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    asset_type = detect_asset_type(ticker)
    asset_label = "crypto asset" if asset_type == "crypto" else "stock"

    with st.chat_message("assistant"):
        status_placeholder = st.empty()
        status_placeholder.markdown(
            f"🔄 **Analyzing {ticker}** ({asset_label}) for **{trade_date}**...\n\n"
            f"This will take a few minutes. The multi-agent pipeline is running:\n"
            f"1. Analyst team gathering data\n"
            f"2. Bull vs Bear research debate\n"
            f"3. Trader formulating a plan\n"
            f"4. Risk management team evaluation\n"
            f"5. Portfolio manager final decision"
        )

        config = DEFAULT_CONFIG.copy()
        config["llm_provider"] = llm_provider
        config["deep_think_llm"] = deep_model
        config["quick_think_llm"] = quick_model
        config["max_debate_rounds"] = debate_rounds
        config["max_risk_discuss_rounds"] = debate_rounds
        session_api_key = st.session_state.get("api_key")
        if session_api_key:
            config["api_key"] = session_api_key

        st.session_state.running = True
        try:
            final_state, decision = run_analysis(ticker, trade_date, config)
            report = format_report(final_state, ticker)

            status_placeholder.empty()
            st.markdown(report)

            st.success(f"**Signal: {decision}**")

            st.session_state.messages.append(
                {"role": "assistant", "content": report + f"\n\n**Signal: {decision}**"}
            )

            report_bytes = report.encode("utf-8")
            st.download_button(
                label="📥 Download Report",
                data=report_bytes,
                file_name=f"{ticker}_{trade_date}_report.md",
                mime="text/markdown",
            )

        except Exception as e:
            status_placeholder.empty()
            error_msg = f"❌ **Analysis failed:** {e}"
            st.error(error_msg)
            st.session_state.messages.append(
                {"role": "assistant", "content": error_msg}
            )
        finally:
            st.session_state.running = False
