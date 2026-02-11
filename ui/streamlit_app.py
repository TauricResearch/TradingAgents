# -*- coding: utf-8 -*-
"""
TradingAgents Streamlit UI

Run from project root:
  pip install streamlit
  streamlit run ui/streamlit_app.py

This UI wraps the same pipeline as the CLI (python -m cli.main analyze).
No business logic is duplicated: the UI builds a selections dict and calls
cli.main.run_analysis_programmatic via ui.cli_wrapper.

How CLI and UI share logic:
- Both use tradingagents.graph.TradingAgentsGraph and cli.main.save_report_to_disk.
- CLI: interactive prompts → run_analysis() with Rich live display.
- UI: form inputs → run_trading_agent() → run_analysis_programmatic() with log_callback.

Adding new agents: extend the graph and config, then add the analyst option
to the sidebar "Analyst / strategy selection" and to cli.models.AnalystType.
"""

from __future__ import annotations

import io
from pathlib import Path
from datetime import datetime, date
from typing import List, Optional

import streamlit as st

# Ensure project root is on path
_UI_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _UI_DIR.parent
if str(_PROJECT_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(_PROJECT_ROOT))

from ui import cli_wrapper

# -----------------------------------------------------------------------------
# Option constants (mirror CLI choices; no business logic)
# -----------------------------------------------------------------------------
LLM_PROVIDERS = [
    ("OpenAI", "openai", "https://api.openai.com/v1"),
    ("Ark (ByteDance)", "ark", "https://ark.ap-southeast.bytepluses.com/api/v3"),
    ("Google", "google", "https://generativelanguage.googleapis.com/v1"),
    ("Anthropic", "anthropic", "https://api.anthropic.com/"),
    ("xAI", "xai", "https://api.x.ai/v1"),
    ("Openrouter", "openrouter", "https://openrouter.ai/api/v1"),
    ("Ollama", "ollama", "http://localhost:11434/v1"),
]

ANALYST_OPTIONS = [
    ("Market", "market"),
    ("Social Media", "social"),
    ("News", "news"),
    ("Fundamentals", "fundamentals"),
]

RESEARCH_DEPTH_OPTIONS = [
    ("Shallow — quick research, few rounds", 1),
    ("Medium — moderate debate rounds", 3),
    ("Deep — comprehensive research", 5),
]

# Per-provider model options (display, value)
SHALLOW_OPTIONS = {
    "openai": [("GPT-5 Mini", "gpt-5-mini"), ("GPT-5 Nano", "gpt-5-nano"), ("GPT-5.2", "gpt-5.2"), ("GPT-4.1", "gpt-4.1")],
    "anthropic": [("Claude Haiku 4.5", "claude-haiku-4-5"), ("Claude Sonnet 4.5", "claude-sonnet-4-5"), ("Claude Sonnet 4", "claude-sonnet-4-20250514")],
    "google": [("Gemini 3 Flash", "gemini-3-flash-preview"), ("Gemini 2.5 Flash", "gemini-2.5-flash"), ("Gemini 2.5 Flash Lite", "gemini-2.5-flash-lite")],
    "xai": [("Grok 4.1 Fast (Non-Reasoning)", "grok-4-1-fast-non-reasoning"), ("Grok 4 Fast (Reasoning)", "grok-4-fast-reasoning")],
    "openrouter": [("NVIDIA Nemotron 3 Nano 30B (free)", "nvidia/nemotron-3-nano-30b-a3b:free"), ("Z.AI GLM 4.5 Air (free)", "z-ai/glm-4.5-air:free")],
    "ollama": [("Qwen3:latest", "qwen3:latest"), ("GPT-OSS:latest", "gpt-oss:latest"), ("GLM-4.7-Flash:latest", "glm-4.7-flash:latest")],
    "ark": [("Ark seed-1-8-251228", "seed-1-8-251228")],
}
DEEP_OPTIONS = {
    "openai": [("GPT-5.2", "gpt-5.2"), ("GPT-5.1", "gpt-5.1"), ("GPT-5", "gpt-5"), ("GPT-4.1", "gpt-4.1"), ("GPT-5 Mini", "gpt-5-mini")],
    "anthropic": [("Claude Sonnet 4.5", "claude-sonnet-4-5"), ("Claude Opus 4.5", "claude-opus-4-5"), ("Claude Haiku 4.5", "claude-haiku-4-5")],
    "google": [("Gemini 3 Pro", "gemini-3-pro-preview"), ("Gemini 3 Flash", "gemini-3-flash-preview"), ("Gemini 2.5 Flash", "gemini-2.5-flash")],
    "xai": [("Grok 4.1 Fast (Reasoning)", "grok-4-1-fast-reasoning"), ("Grok 4 Fast (Reasoning)", "grok-4-fast-reasoning"), ("Grok 4", "grok-4-0709")],
    "openrouter": [("Z.AI GLM 4.5 Air (free)", "z-ai/glm-4.5-air:free"), ("NVIDIA Nemotron 3 Nano 30B (free)", "nvidia/nemotron-3-nano-30b-a3b:free")],
    "ollama": [("GLM-4.7-Flash:latest", "glm-4.7-flash:latest"), ("GPT-OSS:latest", "gpt-oss:latest"), ("Qwen3:latest", "qwen3:latest")],
    "ark": [("Ark seed-1-8-251228", "seed-1-8-251228")],
}


def _default_provider_options(provider_key: str):
    shallow = SHALLOW_OPTIONS.get(provider_key, [("Default", "gpt-5-mini")])
    deep = DEEP_OPTIONS.get(provider_key, [("Default", "gpt-5.2")])
    return shallow, deep


def main() -> None:
    st.set_page_config(
        page_title="TradingAgents",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Minimal custom style for a clean, professional look
    st.markdown("""
        <style>
        .stApp { max-width: 1400px; margin: 0 auto; }
        .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
        div[data-testid="stVerticalBlock"] > div:has(> div[data-testid="stMarkdown"]) { margin-bottom: 0.5rem; }
        .report-preview { font-size: 0.9rem; line-height: 1.5; }
        </style>
    """, unsafe_allow_html=True)

    # ----- Sidebar -----
    with st.sidebar:
        st.markdown("## 📊 TradingAgents")
        st.markdown("---")
        st.markdown("### Agent / strategy selection")
        selected_analysts: List[str] = st.multiselect(
            "Analyst team",
            options=[v for _, v in ANALYST_OPTIONS],
            default=["market", "news", "fundamentals"],
            format_func=lambda x: next(d for d, v in ANALYST_OPTIONS if v == x),
        )
        if not selected_analysts:
            st.warning("Select at least one analyst.")
        st.markdown("### Symbols")
        ticker_input = st.text_input("Ticker symbol(s)", value="SPY", help="Primary symbol; multi-symbol support can be extended.")
        ticker = (ticker_input or "SPY").strip().upper().split()[0]
        st.markdown("### Date range")
        today = date.today()
        analysis_date = st.date_input("Analysis date", value=today, max_value=today)
        analysis_date_str = analysis_date.strftime("%Y-%m-%d")
        st.markdown("### Capital / risk (optional)")
        capital = st.number_input("Capital (reserved)", min_value=0.0, value=100000.0, step=10000.0, format="%.0f")
        risk_pct = st.slider("Risk % (reserved)", 0.0, 50.0, 2.0, 0.5)
        st.markdown("### Optional CLI flags")
        research_depth_label, research_depth = st.selectbox(
            "Research depth",
            options=RESEARCH_DEPTH_OPTIONS,
            index=1,
            format_func=lambda x: x[0],
        )
        research_depth_value = research_depth
        provider_display, provider_key, backend_url = st.selectbox(
            "LLM provider",
            options=LLM_PROVIDERS,
            index=0,
            format_func=lambda x: x[0],
        )
        shallow_opts, deep_opts = _default_provider_options(provider_key)
        shallow_thinker = st.selectbox("Quick-thinking model", options=[v for _, v in shallow_opts], format_func=lambda x: next(d for d, v in shallow_opts if v == x))
        deep_thinker = st.selectbox("Deep-thinking model", options=[v for _, v in deep_opts], format_func=lambda x: next(d for d, v in deep_opts if v == x))
        google_thinking = None
        openai_effort = None
        if provider_key == "google":
            google_thinking = st.selectbox("Gemini thinking mode", ["high", "minimal"], index=0)
        elif provider_key == "openai":
            openai_effort = st.selectbox("OpenAI reasoning effort", ["medium", "high", "low"], index=0)
        st.markdown("---")

    # ----- Main area -----
    st.title("TradingAgents")
    st.caption("Multi-Agents LLM Financial Trading — same pipeline as CLI, no logic duplication.")

    run_clicked = st.button("Run Trading Agent", type="primary", use_container_width=True)

    log_placeholder = st.empty()
    report_placeholder = st.empty()
    download_placeholder = st.empty()
    error_placeholder = st.empty()

    # Clear previous result when starting a new run
    if run_clicked:
        error_placeholder.empty()
        download_placeholder.empty()
        report_placeholder.empty()
        log_lines: List[str] = []

        def on_log(line: str) -> None:
            log_lines.append(line)

        with st.spinner("Running pipeline…"):
            selections = {
                "ticker": ticker,
                "analysis_date": analysis_date_str,
                "analysts": selected_analysts if selected_analysts else ["market", "news", "fundamentals"],
                "research_depth": research_depth_value,
                "llm_provider": provider_key,
                "backend_url": backend_url,
                "shallow_thinker": shallow_thinker,
                "deep_thinker": deep_thinker,
                "google_thinking_level": google_thinking,
                "openai_reasoning_effort": openai_effort,
            }
            success, report_path, err_msg, final_state = cli_wrapper.run_trading_agent(selections, log_callback=on_log)

        with log_placeholder:
            st.markdown("#### Live execution log")
            st.text_area("Log", value="\n".join(log_lines), height=280, key="run_log", label_visibility="collapsed")

        if not success:
            error_placeholder.error(f"Run failed: {err_msg}")
        else:
            st.success("Run completed. Report saved.")
            preview_md = cli_wrapper.build_report_preview_markdown(final_state, ticker)
            with report_placeholder:
                st.markdown("### Report preview")
                if preview_md:
                    st.markdown(preview_md, unsafe_allow_html=False)
                else:
                    st.info("No preview content.")
            if report_path and report_path.exists():
                report_bytes = report_path.read_text(encoding="utf-8")
                download_placeholder.download_button(
                    "Download report (complete_report.md)",
                    data=report_bytes,
                    file_name=report_path.name,
                    mime="text/markdown",
                    use_container_width=True,
                )

    with st.sidebar:
        st.markdown("---")
        st.markdown("**Docs**")
        st.markdown("- CLI: `python -m cli.main analyze`")
        st.markdown("- UI: `streamlit run ui/streamlit_app.py`")


if __name__ == "__main__":
    main()
