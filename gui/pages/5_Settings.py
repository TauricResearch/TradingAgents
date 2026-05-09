"""Settings page — API keys + default run configuration.

Keys stored in ~/.tradingagents/gui_config.json (chmod 0600). Keys present
in the process env (e.g. via .env) are shown as already-set and override
the config-file values, so existing CLI workflows keep working.
"""

from __future__ import annotations

import os

import streamlit as st

from gui.config import (
    DATA_VENDORS,
    GUI_CONFIG_PATH,
    LLM_PROVIDERS,
    PROVIDER_KEYS,
    PROVIDER_LABELS,
    load,
    model_choices_for,
    save,
)
from tradingagents.default_config import DEFAULT_CONFIG

st.set_page_config(page_title="Settings · TradingAgents", layout="wide")

st.title("Settings")
st.caption(
    f"Stored locally at `{GUI_CONFIG_PATH}` (chmod 0600). Never transmitted off your machine."
)

cfg = load()

# ---- API keys ---------------------------------------------------------
st.subheader("API keys")
st.caption(
    "Keys present in your shell / `.env` always win — those rows are read-only here. "
    "Type a value to override or add a new key for a provider."
)
with st.form("api_keys"):
    new_keys = {}
    for provider, env_name in PROVIDER_KEYS.items():
        env_val = os.environ.get(env_name)
        cfg_val = cfg["api_keys"].get(env_name, "")
        col1, col2, col3 = st.columns([2, 4, 1])
        col1.markdown(f"**{PROVIDER_LABELS.get(provider, provider)}**  \n`{env_name}`")
        if env_val:
            col2.text_input(env_name, value="•••• (from environment)",
                            disabled=True, key=f"key_{env_name}_env",
                            label_visibility="collapsed")
            col3.success("env")
        else:
            entered = col2.text_input(
                env_name, value=cfg_val, type="password",
                key=f"key_{env_name}", label_visibility="collapsed",
                placeholder="(not set)",
            )
            new_keys[env_name] = entered
            col3.markdown(":material/key: saved" if cfg_val else ":material/key_off: empty")

    if st.form_submit_button("Save API keys", type="primary"):
        cfg["api_keys"] = {k: v for k, v in new_keys.items() if v}
        save(cfg)
        st.success("Saved.")
        st.rerun()

st.divider()

# ---- Defaults --------------------------------------------------------
st.subheader("Default run configuration")
st.caption("Pre-fills the **Run** page form. Override anything per-run there.")

defaults = cfg["defaults"]

# Provider lives OUTSIDE the form so changing it rebuilds the model dropdowns
# immediately. Form widgets only rerun on submit, which would make the model
# lists stale until you saved.
provider = st.selectbox(
    "LLM provider", LLM_PROVIDERS,
    index=LLM_PROVIDERS.index(defaults.get("llm_provider", "openai")),
    format_func=lambda p: PROVIDER_LABELS.get(p, p),
    key="settings_provider",
    help="Change this first — model dropdowns below will update.",
)

with st.form("defaults"):
    deep_values, deep_labels = model_choices_for(provider, "deep")
    quick_values, quick_labels = model_choices_for(provider, "quick")
    saved_deep = defaults.get("deep_think_llm", "")
    saved_quick = defaults.get("quick_think_llm", "")
    # Promote the saved value to the front of the list if the catalog
    # doesn't include it, so the dropdown lands on something familiar.
    if saved_deep and saved_deep not in deep_values:
        deep_values = [saved_deep] + deep_values
    if saved_quick and saved_quick not in quick_values:
        quick_values = [saved_quick] + quick_values

    c1, c2 = st.columns(2)
    deep_model = c1.selectbox(
        "Deep-think model", deep_values,
        index=deep_values.index(saved_deep) if saved_deep in deep_values else 0,
        format_func=lambda v: deep_labels.get(v, v),
        accept_new_options=True,
        key=f"settings_deep_{provider}",
        help="Pick from the catalog or type any model id.",
    )
    quick_model = c2.selectbox(
        "Quick-think model", quick_values,
        index=quick_values.index(saved_quick) if saved_quick in quick_values else 0,
        format_func=lambda v: quick_labels.get(v, v),
        accept_new_options=True,
        key=f"settings_quick_{provider}",
        help="Pick from the catalog or type any model id.",
    )
    backend_url = st.text_input(
        "Default custom base URL",
        value=str(defaults.get("backend_url") or ""),
        placeholder="https://your-openai-compatible-endpoint/v1",
        help=(
            "Optional OpenAI-compatible API base URL used by default for runs "
            "and follow-up chat. Leave blank for provider defaults."
        ),
    ).strip()

    c4, c5 = st.columns(2)
    debate_rounds = c4.slider("Bull/Bear debate rounds", 1, 5,
                              value=int(defaults.get("max_debate_rounds", 1)))
    risk_rounds = c5.slider("Risk discussion rounds", 1, 5,
                            value=int(defaults.get("max_risk_discuss_rounds", 1)))

    output_lang = st.text_input("Output language",
                                value=defaults.get("output_language", "English"),
                                help="Final reports use this language; internal debate stays in English.")

    st.markdown("**Default data vendors**")
    v_default = defaults.get("data_vendors", DEFAULT_CONFIG["data_vendors"])
    cv1, cv2, cv3, cv4 = st.columns(4)
    v_core = cv1.selectbox("Stock data", DATA_VENDORS,
                           index=DATA_VENDORS.index(v_default.get("core_stock_apis", "yfinance")))
    v_tech = cv2.selectbox("Technical", DATA_VENDORS,
                           index=DATA_VENDORS.index(v_default.get("technical_indicators", "yfinance")))
    v_fund = cv3.selectbox("Fundamentals", DATA_VENDORS,
                           index=DATA_VENDORS.index(v_default.get("fundamental_data", "yfinance")))
    v_news = cv4.selectbox("News", DATA_VENDORS,
                           index=DATA_VENDORS.index(v_default.get("news_data", "yfinance")))

    checkpoint = st.checkbox("Enable LangGraph checkpoint resume",
                             value=bool(defaults.get("checkpoint_enabled", False)),
                             help="Saves state after each node so a crashed run can resume.")

    if st.form_submit_button("Save defaults", type="primary"):
        cfg["defaults"] = {
            "llm_provider": provider,
            "deep_think_llm": deep_model,
            "quick_think_llm": quick_model,
            "backend_url": backend_url,
            "max_debate_rounds": debate_rounds,
            "max_risk_discuss_rounds": risk_rounds,
            "output_language": output_lang,
            "data_vendors": {
                "core_stock_apis": v_core,
                "technical_indicators": v_tech,
                "fundamental_data": v_fund,
                "news_data": v_news,
            },
            "checkpoint_enabled": checkpoint,
        }
        save(cfg)
        st.success("Saved.")
        st.rerun()

st.divider()
st.caption(
    "**Reminder:** the framework's default model names (e.g. `gpt-5.4-mini`) are "
    "placeholders. Use real model identifiers your provider supports — for example "
    "`gpt-4o`, `gpt-4o-mini`, `claude-sonnet-4-5`, `claude-haiku-4-5`, "
    "`gemini-2.5-flash`, or `deepseek-chat`."
)
