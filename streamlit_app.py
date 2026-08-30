"""
TradingAgents Streamlit App — Web-Interface für das Multi-Agent-Trading-Framework.
Deployed auf trading-agents.markb.de
"""

import datetime
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, "/opt/data/trading-agents")

from handelsagenten.default_config import DEFAULT_CONFIG
from handelsagenten.graph.trading_graph import TradingAgentsGraph
from handelsagenten.llm_clients.model_catalog import MODEL_OPTIONS

st.set_page_config(
    page_title="Trading Agents",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# === CSS ===
st.markdown("""
<style>
    .main-header { font-size: 2rem; font-weight: 700; margin-bottom: 0.5rem; }
    .sub-header { color: #888; margin-bottom: 1.5rem; }
    .metric-card {
        background: #1e1e1e;
        border-radius: 10px;
        padding: 1rem;
        margin: 0.5rem 0;
        border: 1px solid #333;
    }
    .decision-buy { color: #4caf50; font-weight: bold; font-size: 2rem; }
    .decision-sell { color: #f44336; font-weight: bold; font-size: 2rem; }
    .decision-hold { color: #ff9800; font-weight: bold; font-size: 2rem; }
    .stButton > button { width: 100%; }
    .report-section {
        background: #1a1a2e;
        border-radius: 8px;
        padding: 1.2rem;
        margin: 0.8rem 0;
        border-left: 3px solid #4a90d9;
    }
    .report-section h3 { margin-top: 0; color: #4a90d9; }
</style>
""", unsafe_allow_html=True)

# === Provider-Mapping ===
PROVIDER_LABELS = {
    "openai": "OpenAI (GPT)",
    "anthropic": "Anthropic (Claude)",
    "google": "Google (Gemini)",
    "xai": "xAI (Grok)",
    "deepseek": "DeepSeek",
    "qwen": "Qwen (Alibaba)",
    "qwen-cn": "Qwen CN (Alibaba China)",
    "glm": "GLM (Zhipu)",
    "glm-cn": "GLM CN (BigModel)",
    "minimax": "MiniMax",
    "minimax-cn": "MiniMax CN",
    "ollama": "Ollama (lokal)",
    "openai_compatible": "OpenAI-kompatibel",
    "mistral": "Mistral",
    "kimi": "Kimi",
    "groq": "Groq",
    "nvidia": "NVIDIA",
    "bedrock": "AWS Bedrock",
}

# === Erweiterte OpenAI-Modelle ===
OPENAI_EXTRA_MODELS = {
    "deep": [
        ("GPT-4o - Omni flagship, multimodal (sicher)", "gpt-4o"),
        ("GPT-4 Turbo - Fast, cost-effective", "gpt-4-turbo"),
        ("GPT-4 - Original flagship", "gpt-4"),
        ("GPT-4.1 - Latest GPT-4, 1M context", "gpt-4.1"),
        ("o3 - Advanced reasoning", "o3"),
        ("o1 - Deep reasoning", "o1"),
        ("o1-mini - Fast reasoning", "o1-mini"),
        ("GPT-5.5 - Latest frontier, 1M context", "gpt-5.5"),
        ("GPT-5.5 Pro - Most capable, expensive", "gpt-5.5-pro"),
        ("GPT-5.4 - Previous-gen frontier, 1M context", "gpt-5.4"),
        ("GPT-5.2 - Strong reasoning, cost-effective", "gpt-5.2"),
        ("Custom model ID", "custom"),
    ],
    "quick": [
        ("GPT-4o Mini - Small, fast, cheap (sicher)", "gpt-4o-mini"),
        ("GPT-3.5 Turbo - Legacy, very cheap (sicher)", "gpt-3.5-turbo"),
        ("GPT-4.1 Mini - Fast GPT-4 class", "gpt-4.1-mini"),
        ("GPT-4.1 Nano - Cheapest GPT-4", "gpt-4.1-nano"),
        ("GPT-5.4 Mini - Fast, strong coding", "gpt-5.4-mini"),
        ("GPT-5.4 Nano - Cheapest, high-volume", "gpt-5.4-nano"),
        ("GPT-5.5 - Latest frontier, 1M context", "gpt-5.5"),
        ("Custom model ID", "custom"),
    ],
}

ANTHROPIC_EXTRA_MODELS = {
    "deep": [
        ("Claude Fable 5 - Most capable, long-running agents", "claude-fable-5"),
        ("Claude Opus 4.8 - Frontier agentic coding", "claude-opus-4-8"),
        ("Claude Opus 4.7 - Previous frontier", "claude-opus-4-7"),
        ("Claude Opus 4 - Original Opus 4", "claude-opus-4"),
        ("Claude Sonnet 5 - Near-frontier at Sonnet cost", "claude-sonnet-5"),
        ("Claude Sonnet 4 - Previous Sonnet", "claude-sonnet-4"),
        ("Custom model ID", "custom"),
    ],
    "quick": [
        ("Claude Sonnet 5 - Best speed/intelligence balance", "claude-sonnet-5"),
        ("Claude Haiku 4.5 - Fastest near-frontier", "claude-haiku-4-5"),
        ("Claude Haiku 3.5 - Very fast, cheap", "claude-haiku-3-5"),
        ("Custom model ID", "custom"),
    ],
}

GOOGLE_EXTRA_MODELS = {
    "deep": [
        ("Gemini 3.1 Pro - Reasoning-first (preview)", "gemini-3.1-pro-preview"),
        ("Gemini 3.5 Flash - Latest GA, strong agentic", "gemini-3.5-flash"),
        ("Gemini 2.5 Pro - Previous flagship", "gemini-2.5-pro"),
        ("Gemini 2.5 Flash - Fast previous-gen", "gemini-2.5-flash"),
        ("Custom model ID", "custom"),
    ],
    "quick": [
        ("Gemini 3.5 Flash - Latest, frontier agentic", "gemini-3.5-flash"),
        ("Gemini 3.1 Flash Lite - Most cost-efficient", "gemini-3.1-flash-lite"),
        ("Gemini 2.5 Flash - Fast, cheap", "gemini-2.5-flash"),
        ("Custom model ID", "custom"),
    ],
}

DEEPSEEK_EXTRA_MODELS = {
    "deep": [
        ("DeepSeek V4 Pro - Latest flagship", "deepseek-v4-pro"),
        ("DeepSeek V4 Flash - Fast, supports thinking", "deepseek-v4-flash"),
        ("DeepSeek V3 - Previous flagship", "deepseek-v3"),
        ("DeepSeek R1 - Reasoning specialist", "deepseek-r1"),
        ("Custom model ID", "custom"),
    ],
    "quick": [
        ("DeepSeek V4 Flash - Latest fast model", "deepseek-v4-flash"),
        ("DeepSeek V3 - Previous flagship", "deepseek-v3"),
        ("Custom model ID", "custom"),
    ],
}

XAI_EXTRA_MODELS = {
    "deep": [
        ("Grok 4.3 - Latest flagship, 1M ctx", "grok-4.3"),
        ("Grok 4.20 (Reasoning) - Previous-gen", "grok-4.20-0309-reasoning"),
        ("Grok 4.20 Multi-Agent - Multi-agent", "grok-4.20-multi-agent-0309"),
        ("Grok 3 - Earlier flagship", "grok-3"),
        ("Custom model ID", "custom"),
    ],
    "quick": [
        ("Grok 4.3 - Latest flagship, fast", "grok-4.3"),
        ("Grok 4.20 (Non-Reasoning) - Speed-optimized", "grok-4.20-0309-non-reasoning"),
        ("Grok Build 0.1 - Coding-specialized", "grok-build-0.1"),
        ("Custom model ID", "custom"),
    ],
}

EXTRA_MODELS = {
    "openai": OPENAI_EXTRA_MODELS,
    "anthropic": ANTHROPIC_EXTRA_MODELS,
    "google": GOOGLE_EXTRA_MODELS,
    "deepseek": DEEPSEEK_EXTRA_MODELS,
    "xai": XAI_EXTRA_MODELS,
}

def get_model_options(provider, mode):
    if provider in EXTRA_MODELS:
        return EXTRA_MODELS[provider].get(mode, [])
    return MODEL_OPTIONS.get(provider, {}).get(mode, [])

# === Populäre Ticker-Datenbank ===
POPULAR_TICKERS = {
    "🇺🇸 US Tech": [
        ("AAPL — Apple Inc.", "AAPL"), ("MSFT — Microsoft Corp.", "MSFT"),
        ("GOOGL — Alphabet (Google)", "GOOGL"), ("AMZN — Amazon.com", "AMZN"),
        ("NVDA — NVIDIA Corp.", "NVDA"), ("META — Meta Platforms", "META"),
        ("TSLA — Tesla Inc.", "TSLA"), ("AMD — Advanced Micro Devices", "AMD"),
        ("INTC — Intel Corp.", "INTC"), ("NFLX — Netflix Inc.", "NFLX"),
        ("ADBE — Adobe Inc.", "ADBE"), ("CRM — Salesforce", "CRM"),
        ("ORCL — Oracle Corp.", "ORCL"), ("CSCO — Cisco Systems", "CSCO"),
        ("PLTR — Palantir Technologies", "PLTR"),
    ],
    "🇺🇸 US Indizes & ETFs": [
        ("SPY — S&P 500 ETF", "SPY"), ("QQQ — Nasdaq 100 ETF", "QQQ"),
        ("DIA — Dow Jones ETF", "DIA"), ("IWM — Russell 2000 ETF", "IWM"),
        ("VTI — Total US Market", "VTI"), ("VOO — Vanguard S&P 500", "VOO"),
        ("ARKK — ARK Innovation ETF", "ARKK"), ("SOXX — Semiconductor ETF", "SOXX"),
        ("XLF — Financial Sector ETF", "XLF"), ("XLE — Energy Sector ETF", "XLE"),
    ],
    "🇺🇸 US Finance & Sonstige": [
        ("JPM — JPMorgan Chase", "JPM"), ("BAC — Bank of America", "BAC"),
        ("GS — Goldman Sachs", "GS"), ("BRK-B — Berkshire Hathaway", "BRK-B"),
        ("JNJ — Johnson & Johnson", "JNJ"), ("WMT — Walmart Inc.", "WMT"),
        ("XOM — Exxon Mobil", "XOM"), ("DIS — Walt Disney", "DIS"),
        ("BA — Boeing Co.", "BA"), ("NKE — Nike Inc.", "NKE"),
        ("COIN — Coinbase Global", "COIN"), ("GME — GameStop Corp.", "GME"),
    ],
    "🇩🇪 Deutschland": [
        ("SAP — SAP SE", "SAP"), ("DTE.DE — Deutsche Telekom", "DTE.DE"),
        ("SIE.DE — Siemens AG", "SIE.DE"), ("ALV.DE — Allianz SE", "ALV.DE"),
        ("VOW3.DE — Volkswagen AG", "VOW3.DE"), ("BMW.DE — BMW AG", "BMW.DE"),
        ("MBG.DE — Mercedes-Benz", "MBG.DE"), ("BAS.DE — BASF SE", "BAS.DE"),
        ("BAYN.DE — Bayer AG", "BAYN.DE"), ("DB1.DE — Deutsche Börse", "DB1.DE"),
        ("DAX — DAX ETF", "DAX"),
    ],
    "🇪🇺 Europa": [
        ("ASML — ASML Holding", "ASML"), ("AZN.L — AstraZeneca", "AZN.L"),
        ("HSBA.L — HSBC Holdings", "HSBA.L"), ("NESN.SW — Nestlé SA", "NESN.SW"),
        ("NOVN.SW — Novartis", "NOVN.SW"), ("ROG.SW — Roche Holding", "ROG.SW"),
        ("SHEL.L — Shell plc", "SHEL.L"), ("MC.PA — LVMH", "MC.PA"),
        ("SAN.PA — Sanofi", "SAN.PA"),
    ],
    "🇯🇵 Japan": [
        ("7203.T — Toyota Motor", "7203.T"), ("6758.T — Sony Group", "6758.T"),
        ("9984.T — SoftBank Group", "9984.T"), ("8306.T — Mitsubishi UFJ", "8306.T"),
        ("6861.T — Keyence Corp.", "6861.T"), ("6501.T — Hitachi Ltd.", "6501.T"),
    ],
    "🇭🇰 Hong Kong / China": [
        ("0700.HK — Tencent Holdings", "0700.HK"), ("9988.HK — Alibaba Group", "9988.HK"),
        ("0941.HK — China Mobile", "0941.HK"), ("2318.HK — Ping An Insurance", "2318.HK"),
        ("1810.HK — Xiaomi Corp.", "1810.HK"), ("9618.HK — JD.com", "9618.HK"),
    ],
    "🪙 Krypto": [
        ("BTC-USD — Bitcoin", "BTC-USD"), ("ETH-USD — Ethereum", "ETH-USD"),
        ("SOL-USD — Solana", "SOL-USD"), ("XRP-USD — Ripple", "XRP-USD"),
        ("DOGE-USD — Dogecoin", "DOGE-USD"), ("ADA-USD — Cardano", "ADA-USD"),
    ],
    "🌍 Emerging Markets": [
        ("RELIANCE.NS — Reliance Industries", "RELIANCE.NS"),
        ("TCS.NS — Tata Consultancy", "TCS.NS"), ("INFY — Infosys (US)", "INFY"),
        ("TSM — Taiwan Semiconductor", "TSM"), ("BABA — Alibaba (US)", "BABA"),
        ("PBR — Petrobras", "PBR"),
    ],
}

ALL_TICKER_OPTIONS = []
TICKER_MAP = {}
for category, tickers in POPULAR_TICKERS.items():
    for label, symbol in tickers:
        key = f"{label}  [{category}]"
        ALL_TICKER_OPTIONS.append(key)
        TICKER_MAP[key] = symbol

# === Session State ===
if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None
if "analysis_ticker" not in st.session_state:
    st.session_state.analysis_ticker = None
if "analysis_date" not in st.session_state:
    st.session_state.analysis_date = None

# === Header ===
st.markdown('<div class="main-header">📈 TradingAgents</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Multi-Agent LLM Financial Trading Framework</div>', unsafe_allow_html=True)

# === Sidebar ===
with st.sidebar:
    st.header("⚙️ Konfiguration")

    # Ticker
    st.subheader("📊 Ticker")
    ticker_search = st.selectbox(
        "Ticker suchen & auswählen",
        options=[""] + ALL_TICKER_OPTIONS,
        index=0,
        placeholder="z.B. AAPL, NVDA, BTC-USD...",
    )
    if ticker_search:
        ticker = TICKER_MAP.get(ticker_search, ticker_search.split(" — ")[0].strip())
    else:
        ticker = ""

    with st.expander("✏️ Oder manuell eingeben", expanded=False):
        manual_ticker = st.text_input("Ticker manuell", value="", placeholder="z.B. AAPL").strip().upper()
        if manual_ticker:
            ticker = manual_ticker
    if not ticker:
        ticker = "AAPL"
    st.caption(f"Ausgewählt: **{ticker}**")

    analysis_date = st.date_input(
        "📅 Analyse-Datum",
        value=datetime.date.today() - datetime.timedelta(days=1),
        max_value=datetime.date.today(),
    )

    st.divider()

    # === LLM Provider & Modelle ===
    st.subheader("🤖 LLM Provider & Modell")

    provider_keys = list(MODEL_OPTIONS.keys())
    provider_labels = [f"{PROVIDER_LABELS.get(k, k)} ({k})" for k in provider_keys]
    selected_provider_idx = st.selectbox(
        "Provider",
        options=range(len(provider_keys)),
        format_func=lambda i: provider_labels[i],
        index=0,
        key="provider_select",
    )
    llm_provider = provider_keys[selected_provider_idx]

    deep_options = get_model_options(llm_provider, "deep")
    if deep_options:
        deep_labels = [f"{label} ({model_id})" for label, model_id in deep_options]
        deep_idx = st.selectbox(
            "🧠 Deep Think Model",
            options=range(len(deep_options)),
            format_func=lambda i: deep_labels[i],
            index=0,
            key="deep_model",
        )
        deep_think_llm = deep_options[deep_idx][1]
    else:
        deep_think_llm = st.text_input("🧠 Deep Think Model", value="gpt-4o")

    quick_options = get_model_options(llm_provider, "quick")
    if quick_options:
        quick_labels = [f"{label} ({model_id})" for label, model_id in quick_options]
        quick_idx = st.selectbox(
            "⚡ Quick Think Model",
            options=range(len(quick_options)),
            format_func=lambda i: quick_labels[i],
            index=0,
            key="quick_model",
        )
        quick_think_llm = quick_options[quick_idx][1]
    else:
        quick_think_llm = st.text_input("⚡ Quick Think Model", value="gpt-4o-mini")

    if deep_think_llm == "custom":
        deep_think_llm = st.text_input("🧠 Custom Deep Model ID", value="gpt-4o", key="custom_deep")
    if quick_think_llm == "custom":
        quick_think_llm = st.text_input("⚡ Custom Quick Model ID", value="gpt-4o-mini", key="custom_quick")

    st.divider()

    with st.expander("🔬 Research-Einstellungen", expanded=False):
        max_debate_rounds = st.slider("Max Debate Rounds", 1, 5, 2)
        selected_analysts = st.multiselect(
            "Analysten",
            options=["market", "social", "news", "fundamentals"],
            default=["market", "social", "news", "fundamentals"],
            format_func=lambda x: {
                "market": "📊 Market Analyst",
                "social": "💬 Sentiment Analyst",
                "news": "📰 News Analyst",
                "fundamentals": "📋 Fundamentals Analyst",
            }[x],
        )

    st.divider()
    start_analysis = st.button("🚀 Analyse starten", type="primary", use_container_width=True)

# === Main Area ===
if not start_analysis and st.session_state.analysis_result is None:
    st.info("👈 Konfiguriere deine Analyse in der Sidebar und klicke auf **Analyse starten**.")
    with st.expander("📖 Was ist TradingAgents?", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("""
            **TradingAgents** ist ein Multi-Agent-Trading-Framework, das die Dynamik
            realer Trading-Firmen nachbildet:

            - **Analyst Team**: Fundamental, Sentiment, News & Technical Analysts
            - **Research Team**: Bull & Bear Researchers debattieren
            - **Trader Agent**: Trifft Trading-Entscheidungen
            - **Risk Management**: Bewertet Portfolio-Risiken
            - **Portfolio Manager**: Finale Entscheidung
            """)
        with col2:
            st.markdown("""
            **Unterstützte Märkte:**
            - 🇺🇸 US: `AAPL`, `SPY`
            - 🇭🇰 Hong Kong: `0700.HK`
            - 🇯🇵 Tokyo: `7203.T`
            - 🇬🇧 London: `AZN.L`
            - 🇮🇳 India: `RELIANCE.NS`
            - 🪙 Crypto: `BTC-USD`, `ETH-USD`
            """)

elif start_analysis:
    # === Run Analysis ===
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = llm_provider
    config["deep_think_llm"] = deep_think_llm
    config["quick_think_llm"] = quick_think_llm
    config["temperature"] = 0.3  # Sinnvoller Default für Analysen
    config["max_debate_rounds"] = max_debate_rounds
    config["selected_analysts"] = selected_analysts

    date_str = analysis_date.strftime("%Y-%m-%d")

    st.markdown(f"### 🔍 Analysiere **{ticker}** zum **{date_str}**")
    st.caption(f"Provider: {llm_provider} | Deep: {deep_think_llm} | Quick: {quick_think_llm}")

    progress_bar = st.progress(0, text="Initialisiere...")
    status_container = st.empty()

    try:
        status_container.info("Starte TradingAgentsGraph...")
        ta = TradingAgentsGraph(debug=False, config=config)
        progress_bar.progress(10, text="Sammle Marktdaten & führe Analyse durch...")

        with st.spinner(f"Analysiere {ticker}... Die Multi-Agent-Analyse kann mehrere Minuten dauern."):
            final_state, decision = ta.propagate(ticker, date_str)

        progress_bar.progress(100, text="Analyse abgeschlossen!")
        status_container.success(f"✅ Analyse für {ticker} abgeschlossen!")

        # Save to session state
        st.session_state.analysis_result = final_state
        st.session_state.analysis_ticker = ticker
        st.session_state.analysis_date = date_str
        st.session_state.analysis_decision = decision
        st.rerun()

    except Exception as e:
        progress_bar.progress(0, text="Fehler!")
        status_container.error(f"❌ Fehler: {str(e)}")
        st.exception(e)

# === Show Results (from session state) ===
if st.session_state.analysis_result is not None:
    final_state = st.session_state.analysis_result
    ticker = st.session_state.analysis_ticker
    date_str = st.session_state.analysis_date
    decision = st.session_state.analysis_decision

    st.markdown(f"### 🔍 Analyse: **{ticker}** zum **{date_str}**")

    # === Decision Header ===
    decision_str = str(decision)
    decision_lower = decision_str.lower()

    if "buy" in decision_lower or "long" in decision_lower:
        action = "🟢 BUY"
        action_class = "decision-buy"
    elif "sell" in decision_lower or "short" in decision_lower:
        action = "🔴 SELL"
        action_class = "decision-sell"
    elif "overweight" in decision_lower:
        action = "🟢 OVERWEIGHT"
        action_class = "decision-buy"
    elif "underweight" in decision_lower:
        action = "🔴 UNDERWEIGHT"
        action_class = "decision-sell"
    else:
        action = "🟡 HOLD"
        action_class = "decision-hold"

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div style="font-size: 0.8rem; color: #888;">ENTSCHEIDUNG</div>
            <div class="{action_class}">{action}</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div style="font-size: 0.8rem; color: #888;">TICKER</div>
            <div style="font-size: 1.5rem;">{ticker}</div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <div style="font-size: 0.8rem; color: #888;">DATUM</div>
            <div style="font-size: 1.5rem;">{date_str}</div>
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # === Analyst Reports ===
    st.markdown("## 📊 Analyst Reports")

    # Market Report
    market_report = final_state.get("market_report", "")
    if market_report:
        with st.expander("📊 Market Analyst Report", expanded=True):
            st.markdown(market_report)

    # Sentiment Report
    sentiment_report = final_state.get("sentiment_report", "")
    if sentiment_report:
        with st.expander("💬 Sentiment Analyst Report", expanded=False):
            st.markdown(sentiment_report)

    # News Report
    news_report = final_state.get("news_report", "")
    if news_report:
        with st.expander("📰 News Analyst Report", expanded=False):
            st.markdown(news_report)

    # Fundamentals Report
    fundamentals_report = final_state.get("fundamentals_report", "")
    if fundamentals_report:
        with st.expander("📋 Fundamentals Analyst Report", expanded=False):
            st.markdown(fundamentals_report)

    st.divider()

    # === Investment Plan & Debate ===
    st.markdown("## 🏛️ Research & Investment Plan")

    investment_plan = final_state.get("investment_plan", "")
    if investment_plan:
        with st.expander("📐 Investment Plan (Research Manager)", expanded=True):
            st.markdown(investment_plan)

    # Debate state
    debate_state = final_state.get("investment_debate_state", {})
    if debate_state:
        bull_hist = debate_state.get("bull_history", "")
        bear_hist = debate_state.get("bear_history", "")
        judge = debate_state.get("judge_decision", "")

        if bull_hist or bear_hist:
            with st.expander("🐂🐻 Bull vs Bear Debate", expanded=False):
                tab1, tab2, tab3 = st.tabs(["🐂 Bull Case", "🐻 Bear Case", "⚖️ Research Manager"])
                with tab1:
                    st.markdown(bull_hist if bull_hist else "*Keine Bull-Analyse*")
                with tab2:
                    st.markdown(bear_hist if bear_hist else "*Keine Bear-Analyse*")
                with tab3:
                    st.markdown(judge if judge else "*Keine Entscheidung*")

    st.divider()

    # === Trader Decision ===
    st.markdown("## 💼 Trader & Risk Management")

    trader_plan = final_state.get("trader_investment_plan", "")
    if trader_plan:
        with st.expander("📈 Trader Investment Decision", expanded=True):
            st.markdown(trader_plan)

    # Risk debate
    risk_state = final_state.get("risk_debate_state", {})
    if risk_state:
        agg = risk_state.get("aggressive_history", "")
        cons = risk_state.get("conservative_history", "")
        neut = risk_state.get("neutral_history", "")
        risk_judge = risk_state.get("judge_decision", "")

        if agg or cons or neut:
            with st.expander("⚠️ Risk Management Debate", expanded=False):
                rt1, rt2, rt3, rt4 = st.tabs([
                    "🔥 Aggressive", "🛡️ Conservative", "⚖️ Neutral", "📋 Portfolio Manager"
                ])
                with rt1:
                    st.markdown(agg if agg else "*Keine Analyse*")
                with rt2:
                    st.markdown(cons if cons else "*Keine Analyse*")
                with rt3:
                    st.markdown(neut if neut else "*Keine Analyse*")
                with rt4:
                    st.markdown(risk_judge if risk_judge else "*Keine Entscheidung*")

    st.divider()

    # === Final Decision ===
    st.markdown("## 🎯 Final Trade Decision")
    final_decision = final_state.get("final_trade_decision", "")
    if final_decision:
        st.markdown(f'<div class="report-section">{final_decision}</div>', unsafe_allow_html=True)
    else:
        st.markdown(decision_str)

    st.divider()

    # === Save Report ===
    col_save, col_reset = st.columns([1, 1])
    with col_save:
        if st.button("💾 Report speichern", use_container_width=True):
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            report_dir = Path("/opt/data/trading-agents/reports")
            report_dir.mkdir(exist_ok=True)
            report_path = report_dir / f"{ticker}_{timestamp}.md"

            # Build comprehensive report
            report = f"""# TradingAgents Report: {ticker}

**Datum:** {date_str}
**Provider:** {llm_provider}
**Deep Model:** {deep_think_llm}
**Quick Model:** {quick_think_llm}

## Entscheidung: {action}

---

## Market Analyst Report
{market_report}

## Sentiment Analyst Report
{sentiment_report}

## News Analyst Report
{news_report}

## Fundamentals Analyst Report
{fundamentals_report}

## Investment Plan
{investment_plan}

## Bull vs Bear Debate
### Bull Case
{bull_hist if debate_state else 'N/A'}

### Bear Case
{bear_hist if debate_state else 'N/A'}

### Research Manager Decision
{judge if debate_state else 'N/A'}

## Trader Decision
{trader_plan}

## Risk Management
### Aggressive
{agg if risk_state else 'N/A'}

### Conservative
{cons if risk_state else 'N/A'}

### Neutral
{neut if risk_state else 'N/A'}

### Portfolio Manager
{risk_judge if risk_state else 'N/A'}

## Final Trade Decision
{final_decision}
"""
            report_path.write_text(report)
            st.success(f"✅ Report gespeichert: `{report_path}`")

    with col_reset:
        if st.button("🔄 Neue Analyse", use_container_width=True):
            st.session_state.analysis_result = None
            st.rerun()
