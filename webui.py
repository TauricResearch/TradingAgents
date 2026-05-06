"""Streamlit web UI for TradingAgents — with live streaming, i18n, fuzzy ticker resolution.

Run locally:
    streamlit run webui.py

Expose to LAN / remote friends:
    streamlit run webui.py --server.address 0.0.0.0 --server.port 8501
"""
import datetime as _dt
import hashlib
import os
import re
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Optional

import streamlit as st
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent
load_dotenv(_ROOT / ".env")
load_dotenv(_ROOT / ".env.enterprise", override=False)

from auth import gate as _auth_gate, sign_out as _auth_sign_out
from ticker_resolver import resolve_ticker
from tradingagents.agents.utils.memory import TradingMemoryLog
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.checkpointer import (
    checkpoint_step,
    clear_all_checkpoints,
)
import notify
import user_prefs
from tradingagents.dataflows.user_research import (
    clear_run_dir,
    delete_research,
    ingest_research,
    list_research,
)
from tradingagents.llm_clients import create_llm_client


# Concurrency: each analysis runs in its own subprocess (worker.py), so the
# tradingagents module-level _config global no longer races. A semaphore caps
# total concurrent workers to keep the host from melting under load.
@st.cache_resource
def _run_semaphore():
    n = int(os.getenv("MAX_CONCURRENT_RUNS", "4"))
    return threading.Semaphore(n)


@st.cache_resource
def _running_state():
    """Live registry of in-flight runs. Keyed by run-id (email+ticker+date)."""
    return {"runs": {}}


def _user_home_for(email: str) -> Path:
    """Hash-derived per-user data root. Hash keeps emails out of the FS tree."""
    slug = hashlib.sha256(email.strip().lower().encode()).hexdigest()[:12]
    home = Path.home() / ".tradingagents" / "users" / slug
    home.mkdir(parents=True, exist_ok=True)
    return home


# ════════════════════════════════════════════════════════════════════
# Range stats card (pre-analysis, cached)
# ════════════════════════════════════════════════════════════════════
@st.cache_data(show_spinner=False, ttl=15 * 60)
def _range_stats_cached(t: str, d: str):
    """Memoized fetch+format for the range-stats card. Returns None on
    RangeStatsUnavailable; lets other exceptions bubble (caller renders fallback)."""
    from tradingagents.dataflows.range_stats import (
        RangeStatsUnavailable,
        compute_range_stats,
        format_range_stats_for_webui,
    )
    try:
        return format_range_stats_for_webui(compute_range_stats(t, d))
    except RangeStatsUnavailable:
        return None


def _render_range_stats_card(ticker: str, trade_date_str: str) -> None:
    """Render a 3-column close/open/volume range stats card.

    Failures degrade silently to a one-line note — never block the page.
    """
    try:
        payload = _range_stats_cached(ticker, trade_date_str)
    except Exception as e:  # noqa: BLE001 — defensive at boundary
        st.caption(f"Range stats unavailable: {e}")
        return

    if payload is None:
        st.info(f"Range stats unavailable for {ticker} on {trade_date_str}.")
        return

    today = payload["today"]
    with st.expander(
        f"📊 Range Stats — {ticker} (today: open={today['open']:,.2f} "
        f"close={today['close']:,.2f} vol={today['volume']:,})",
        expanded=False,
    ):
        cols = st.columns(3)
        for col, (metric_label, metric_key, current_value, is_vol) in zip(
            cols,
            [
                ("Close", "close", today["close"], False),
                ("Open", "open", today["open"], False),
                ("Volume", "volume", today["volume"], True),
            ],
        ):
            cur_str = f"{int(current_value):,}" if is_vol else f"{current_value:,.2f}"
            col.markdown(f"**{metric_label}** — {cur_str}")
            rows = []
            for w in ("52w", "6m", "3m", "1m"):
                d = payload["metrics"][metric_key][w]
                if d["low"] is None:
                    rows.append({"window": w, "low": "n/a", "high": "n/a",
                                 "vs Low": "n/a", "vs High": "n/a", "Pos": "n/a"})
                    continue
                rows.append({
                    "window": w,
                    "low": f"{d['low']:,.2f}" if not is_vol else f"{int(d['low']):,}",
                    "high": f"{d['high']:,.2f}" if not is_vol else f"{int(d['high']):,}",
                    "vs Low": f"{d['pct_above_low']:+.1f}%",
                    "vs High": f"{d['pct_below_high']:+.1f}%",
                    "Pos": f"{d['position_pct']:.0f}%",
                })
            col.dataframe(rows, hide_index=True, use_container_width=True)


st.set_page_config(page_title="TradingAgents", page_icon="📈", layout="wide")

# ════════════════════════════════════════════════════════════════════
# i18n
# ════════════════════════════════════════════════════════════════════
LANG = {
    "en": {
        "ui_lang": "Interface language",
        "title": "TradingAgents",
        "subtitle": "Multi-agent LLM trading framework",
        "ticker": "Ticker / company name",
        "ticker_help": "Type a US ticker (NVDA), an English name (Apple), or a Chinese name (苹果, 英伟达).",
        "resolved_as": "→ resolved as",
        "resolve_failed": "Could not resolve. Will use the input as-is.",
        "date": "Analysis date",
        "provider": "LLM provider",
        "deep_model": "Deep-think model",
        "quick_model": "Quick-think model",
        "key_loaded": "{} loaded ✓",
        "key_missing": "{} not set — add it to .env",
        "analysts": "Analysts",
        "analyst_market": "Market / Technical",
        "analyst_social": "Social / Sentiment",
        "analyst_news": "News & Macro",
        "analyst_fundamentals": "Fundamentals",
        "debate_rounds": "Bull/Bear debate rounds",
        "risk_rounds": "Risk discussion rounds",
        "output_lang": "Report output language",
        "checkpoint_section": "Checkpoint / Resume",
        "checkpoint_enable": "Enable checkpoint resume",
        "checkpoint_help": "Save state after each node so a crashed/interrupted run can resume "
                           "from the last successful step on the next run with the same ticker+date.",
        "checkpoint_resumable": "♻ Resumable checkpoint at step **{}** for {} · {}",
        "checkpoint_fresh": "No prior checkpoint — will start fresh.",
        "checkpoint_clear": "🗑 Clear all checkpoints",
        "checkpoint_cleared": "Deleted {} checkpoint DB(s).",
        "checkpoint_preserved": "Checkpoint preserved for {} · {}. Re-run with the same ticker+date to resume.",
        "run_btn": "▶ Run analysis",
        "intro": "Configure on the left, then click **Run analysis**. "
                 "Reports stream live as each agent produces them — typically the first analyst "
                 "report shows up within 30–60s.",
        "page_title": "Analysis: {} · {}",
        "page_caption": "Provider **{}** · deep `{}` · quick `{}` · analysts: {}",
        "elapsed": "Elapsed",
        "pipeline_label": "Pipeline:",
        "tab_market": "Market",
        "tab_sentiment": "Sentiment",
        "tab_news": "News",
        "tab_fundamentals": "Fundamentals",
        "tab_invest": "Investment Plan",
        "tab_trader": "Trader",
        "tab_risk": "Risk Decision",
        "tab_log": "Activity log",
        "waiting": "_waiting…_",
        "ev_started": "Pipeline started",
        "ev_resuming": "Resuming",
        "ev_resuming_d": "from step {} for {} on {}",
        "ev_started_d": "{} on {}",
        "ev_analyst_done": "{} analyst done",
        "ev_invest_update": "Investment debate update",
        "ev_trader_ready": "Trader plan ready",
        "ev_risk_update": "Risk debate update",
        "ev_complete": "Pipeline complete",
        "ev_error": "ERROR",
        "ev_persist_warn": "Post-run persistence warning",
        "stream_empty": "Stream ended with no chunks.",
        "decision_live": "FINAL DECISION (live)",
        "decision_final": "FINAL DECISION",
        "raw_decision": "Raw decision string",
        "elapsed_s": "elapsed {}s",
        # status names
        "agent_market": "Market", "agent_social": "Social", "agent_news": "News",
        "agent_fundamentals": "Fundamentals",
        "agent_bull": "Bull Researcher", "agent_bear": "Bear Researcher",
        "agent_research_mgr": "Research Manager", "agent_trader": "Trader",
        "agent_risk_agg": "Aggressive Risk", "agent_risk_con": "Conservative Risk",
        "agent_risk_neu": "Neutral Risk", "agent_pm": "Portfolio Manager",
        "sec_bull": "🐂 Bull Researcher", "sec_bear": "🐻 Bear Researcher",
        "sec_research_mgr": "⚖️ Research Manager Decision",
        "sec_risk_agg": "🔥 Aggressive", "sec_risk_con": "🛡️ Conservative",
        "sec_risk_neu": "⚖️ Neutral", "sec_pm": "🧑‍💼 Portfolio Manager",
    },
    "zh": {
        "ui_lang": "界面语言",
        "title": "TradingAgents 交易代理",
        "subtitle": "多智能体大模型交易框架",
        "ticker": "股票代码 / 公司名称",
        "ticker_help": "可输入美股代码（NVDA）、英文名（Apple），或中文名（苹果、英伟达）。",
        "resolved_as": "→ 识别为",
        "resolve_failed": "无法识别，将按原样使用。",
        "date": "分析日期",
        "provider": "大模型供应商",
        "deep_model": "深度思考模型",
        "quick_model": "快速响应模型",
        "key_loaded": "已加载 {} ✓",
        "key_missing": "{} 未设置 — 请在 .env 中填入",
        "analysts": "分析师",
        "analyst_market": "市场 / 技术面",
        "analyst_social": "社交 / 情绪",
        "analyst_news": "新闻与宏观",
        "analyst_fundamentals": "基本面",
        "debate_rounds": "多空辩论轮数",
        "risk_rounds": "风险讨论轮数",
        "output_lang": "报告输出语言",
        "checkpoint_section": "断点续跑",
        "checkpoint_enable": "启用断点续跑",
        "checkpoint_help": "在每个节点完成后保存状态，崩溃或中断后下次同 ticker+日期 运行时自动从上次成功的节点恢复。",
        "checkpoint_resumable": "♻ 检测到可恢复断点 步骤 **{}**（{} · {}）",
        "checkpoint_fresh": "无历史断点 — 将从头开始。",
        "checkpoint_clear": "🗑 清除全部断点",
        "checkpoint_cleared": "已删除 {} 个断点数据库。",
        "checkpoint_preserved": "已保留 {} · {} 的断点，下次同样输入会自动续跑。",
        "run_btn": "▶ 开始分析",
        "intro": "在左侧配置参数，然后点击 **开始分析**。"
                 "每个 agent 完成会实时刷新报告 — 通常首个分析师报告在 30–60 秒内出现。",
        "page_title": "分析：{} · {}",
        "page_caption": "供应商 **{}** · 深度 `{}` · 快速 `{}` · 分析师：{}",
        "elapsed": "已用时",
        "pipeline_label": "流水线：",
        "tab_market": "市场",
        "tab_sentiment": "情绪",
        "tab_news": "新闻",
        "tab_fundamentals": "基本面",
        "tab_invest": "投资方案",
        "tab_trader": "交易员",
        "tab_risk": "风险决策",
        "tab_log": "活动日志",
        "waiting": "_等待中…_",
        "ev_started": "流水线启动",
        "ev_resuming": "恢复执行",
        "ev_resuming_d": "从步骤 {} 恢复（{} · {}）",
        "ev_started_d": "{} · {}",
        "ev_analyst_done": "{} 分析师完成",
        "ev_invest_update": "投资辩论更新",
        "ev_trader_ready": "交易员方案就绪",
        "ev_risk_update": "风险辩论更新",
        "ev_complete": "流水线完成",
        "ev_error": "错误",
        "ev_persist_warn": "运行后持久化警告",
        "stream_empty": "流式输出无任何数据返回。",
        "decision_live": "实时决策",
        "decision_final": "最终决策",
        "raw_decision": "原始决策文本",
        "elapsed_s": "用时 {}s",
        "agent_market": "市场", "agent_social": "社交", "agent_news": "新闻",
        "agent_fundamentals": "基本面",
        "agent_bull": "多方研究员", "agent_bear": "空方研究员",
        "agent_research_mgr": "研究经理", "agent_trader": "交易员",
        "agent_risk_agg": "激进型风险", "agent_risk_con": "保守型风险",
        "agent_risk_neu": "中立型风险", "agent_pm": "投资组合经理",
        "sec_bull": "🐂 多方研究员", "sec_bear": "🐻 空方研究员",
        "sec_research_mgr": "⚖️ 研究经理决策",
        "sec_risk_agg": "🔥 激进派", "sec_risk_con": "🛡️ 保守派",
        "sec_risk_neu": "⚖️ 中立派", "sec_pm": "🧑‍💼 投资组合经理",
    },
}


def T(key: str) -> str:
    """Look up a translation by key in the active UI language."""
    lang = st.session_state.get("ui_lang", "en")
    return LANG[lang].get(key, LANG["en"].get(key, key))




# ════════════════════════════════════════════════════════════════════
# Constants
# ════════════════════════════════════════════════════════════════════
PROVIDER_MODELS = {
    "google": ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro",
               "gemini-3-flash-preview", "gemini-3.1-flash-lite-preview", "gemini-3.1-pro-preview"],
    "openai": ["gpt-5.4-mini", "gpt-5.4", "gpt-5"],
    "anthropic": ["claude-haiku-4-5-20251001", "claude-sonnet-4-6", "claude-opus-4-7"],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "qwen": ["qwen-plus", "qwen-max"],
    "glm": ["glm-4-plus", "glm-4.5"],
    "xai": ["grok-4", "grok-4-mini"],
    "openrouter": ["openai/gpt-5", "anthropic/claude-sonnet-4-6"],
}

PROVIDER_KEY_ENV = {
    "google": "GOOGLE_API_KEY", "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY", "deepseek": "DEEPSEEK_API_KEY",
    "qwen": "DASHSCOPE_API_KEY", "glm": "ZHIPU_API_KEY",
    "xai": "XAI_API_KEY", "openrouter": "OPENROUTER_API_KEY",
}


def _decision_label(text: str) -> str:
    if not text:
        return "—"
    upper = text.upper()
    for word in ("BUY", "SELL", "HOLD"):
        if re.search(rf"\b{word}\b", upper):
            return word
    return "—"


def _decision_color(label: str) -> str:
    return {"BUY": "#16a34a", "SELL": "#dc2626", "HOLD": "#d97706"}.get(label, "#64748b")


def _status_dot(state: str) -> str:
    return {"pending": "⚪", "in_progress": "🟡", "completed": "🟢"}.get(state, "⚪")


# ════════════════════════════════════════════════════════════════════
# Sidebar
# ════════════════════════════════════════════════════════════════════
# Language selector first (everything below depends on it).
# Persist the choice in the URL (?lang=zh) so it survives browser refresh —
# st.session_state alone resets on every reload.
_lang_label = "Language / 语言"
if "ui_lang" not in st.session_state:
    _url_lang = st.query_params.get("lang", "en")
    st.session_state["ui_lang"] = "zh" if _url_lang == "zh" else "en"

_lang_choice = st.sidebar.selectbox(
    _lang_label, ["English", "中文"],
    index=0 if st.session_state["ui_lang"] == "en" else 1,
    key="_ui_lang_widget",
)
_new_lang = "en" if _lang_choice == "English" else "zh"
if _new_lang != st.session_state["ui_lang"] or st.query_params.get("lang") != _new_lang:
    st.session_state["ui_lang"] = _new_lang
    st.query_params["lang"] = _new_lang

# Email-OTP login gate. Blocks until verified.
_authed_email = _auth_gate(st, lang=st.session_state["ui_lang"])
st.sidebar.caption(f"👤 {_authed_email}")
if st.sidebar.button("Sign out / 退出"):
    _auth_sign_out(st)
    st.rerun()

# Per-user data root. All TradingAgents output (memory log, checkpoints, logs)
# lives under this dir, so different friends never see each other's runs.
USER_HOME = _user_home_for(_authed_email)
USER_CACHE_DIR = str(USER_HOME / "cache")
USER_RESULTS_DIR = str(USER_HOME / "logs")
USER_MEMORY_PATH = str(USER_HOME / "memory" / "trading_memory.md")

st.sidebar.title("📈 " + T("title"))
st.sidebar.caption(T("subtitle"))

raw_input = st.sidebar.text_input(T("ticker"), value="NVDA", help=T("ticker_help")).strip()
ticker, resolution_msg = resolve_ticker(raw_input)
if raw_input and ticker and ticker != raw_input.upper():
    st.sidebar.success(T("resolved_as") + f" `{ticker}`")
elif raw_input and not ticker:
    st.sidebar.warning(T("resolve_failed"))

trade_date = st.sidebar.date_input(
    T("date"), value=_dt.date.today() - _dt.timedelta(days=1)
)

st.sidebar.divider()
provider = st.sidebar.selectbox(T("provider"), list(PROVIDER_MODELS.keys()), index=0)
models = PROVIDER_MODELS[provider]
deep_model = st.sidebar.selectbox(T("deep_model"), models, index=min(2, len(models) - 1))
quick_model = st.sidebar.selectbox(T("quick_model"), models, index=0)

key_env = PROVIDER_KEY_ENV.get(provider)
key_present = bool(os.getenv(key_env)) if key_env else True
if key_env:
    if key_present:
        st.sidebar.success(T("key_loaded").format(key_env))
    else:
        st.sidebar.error(T("key_missing").format(key_env))

# ════════════════════════════════════════════════════════════════════
# Research notes upload + per-ticker library
# ════════════════════════════════════════════════════════════════════
if "ur_per_run" not in st.session_state:
    st.session_state["ur_per_run"] = []

if "ur_run_id" not in st.session_state:
    st.session_state["ur_run_id"] = f"run-{int(time.time())}-{os.getpid()}"

if "ur_seen_digests" not in st.session_state:
    st.session_state["ur_seen_digests"] = set()

if ticker:
    _lib_count = len(list_research(USER_HOME, ticker))
    _lib_label = f"📎 Research notes (library: {_lib_count})"
else:
    _lib_label = "📎 Research notes"

with st.sidebar.expander(_lib_label, expanded=False):
    _save_to_lib = st.checkbox(
        f"Save to {ticker} library" if ticker else "Save to ticker library",
        value=True,
        disabled=not ticker,
        key="ur_save_to_lib",
    )
    _uploads = st.file_uploader(
        "Drop PDF / .md / .txt (max 20MB, up to 5 files)",
        type=["pdf", "md", "markdown", "txt"],
        accept_multiple_files=True,
        key="ur_uploader",
    )
    if _uploads and ticker:
        if len(_uploads) > 5:
            st.error("Max 5 files at once.")
        else:
            for _f in _uploads:
                if _f.size > 20 * 1024 * 1024:
                    st.error(f"{_f.name} exceeds 20MB.")
                    continue
                data = _f.getvalue()
                digest = hashlib.sha256(data).hexdigest()[:12]
                if digest in st.session_state["ur_seen_digests"]:
                    continue
                if ticker:
                    lib_hashes = {m["hash"] for m in list_research(USER_HOME, ticker)}
                    if digest in lib_hashes:
                        st.session_state["ur_seen_digests"].add(digest)
                        continue
                with st.spinner(f"Summarizing {_f.name}…"):
                    try:
                        _quick_client = create_llm_client(provider=provider, model=quick_model)
                        _summarize_llm = _quick_client.get_llm()
                        meta = ingest_research(
                            file_bytes=data,
                            filename=_f.name,
                            ticker=ticker if _save_to_lib else None,
                            user_root=USER_HOME,
                            summarize_fn=_summarize_llm,
                            run_id=st.session_state["ur_run_id"] if not _save_to_lib else None,
                        )
                        if not _save_to_lib:
                            st.session_state["ur_per_run"].append(meta)
                        st.session_state["ur_seen_digests"].add(digest)
                        st.success(f"✓ {_f.name} summarized")
                    except Exception as e:  # noqa: BLE001
                        st.error(f"Failed to ingest {_f.name}: {e}")

    if ticker:
        existing = list_research(USER_HOME, ticker)
        if existing:
            st.markdown("**Library**")
            for m in existing:
                cols = st.columns([1, 4, 1])
                key_base = f"ur_{ticker}_{m['hash']}"
                cols[0].checkbox(
                    "include",
                    value=True,
                    key=f"{key_base}_chk",
                    label_visibility="collapsed",
                )
                cols[1].caption(
                    f"{m['filename']} · {m['uploaded_at'][:10]}"
                )
                if cols[2].button("🗑", key=f"{key_base}_del"):
                    delete_research(USER_HOME, ticker, m["hash"])
                    st.rerun()
        else:
            st.caption("Library is empty for this ticker.")

st.sidebar.divider()
st.sidebar.markdown(f"**{T('analysts')}**")
ANALYST_OPTIONS = [
    ("market", T("analyst_market")),
    ("social", T("analyst_social")),
    ("news", T("analyst_news")),
    ("fundamentals", T("analyst_fundamentals")),
]
selected_analysts = [
    code for code, label in ANALYST_OPTIONS
    if st.sidebar.checkbox(label, value=True, key=f"analyst_{code}")
]
debate_rounds = st.sidebar.slider(T("debate_rounds"), 1, 4, 1)
risk_rounds = st.sidebar.slider(T("risk_rounds"), 1, 4, 1)

# Default report-output language follows UI language but is independent
_default_output_lang = "中文" if st.session_state["ui_lang"] == "zh" else "English"
_output_options = ["English", "中文", "日本語", "한국어"]
output_language = st.sidebar.selectbox(
    T("output_lang"), _output_options, index=_output_options.index(_default_output_lang)
)

# Checkpoint controls
st.sidebar.divider()
st.sidebar.markdown(f"**{T('checkpoint_section')}**")
checkpoint_enabled = st.sidebar.checkbox(
    T("checkpoint_enable"), value=False, help=T("checkpoint_help"),
)

_cache_dir = USER_CACHE_DIR
_existing_step = None
if ticker:
    try:
        _existing_step = checkpoint_step(_cache_dir, ticker, str(trade_date))
    except Exception:
        _existing_step = None

if _existing_step is not None:
    st.sidebar.info(T("checkpoint_resumable").format(_existing_step, ticker, trade_date))
elif checkpoint_enabled:
    st.sidebar.caption(T("checkpoint_fresh"))

if st.sidebar.button(T("checkpoint_clear"), use_container_width=True):
    # Only clears THIS user's checkpoints (we pass the per-user cache dir).
    n = clear_all_checkpoints(_cache_dir)
    st.sidebar.success(T("checkpoint_cleared").format(n))

# ─── Daily-schedule preferences ───
st.sidebar.divider()
_is_zh = st.session_state["ui_lang"] == "zh"
_prefs_title = "📅 每日定时分析" if _is_zh else "📅 Daily schedule"
_prefs = user_prefs.load(_authed_email)

with st.sidebar.expander(_prefs_title, expanded=False):
    _enable = st.checkbox(
        ("每天自动分析并推送到 Telegram" if _is_zh
         else "Run daily and push to Telegram"),
        value=bool(_prefs.get("daily_schedule_enabled")),
        key="prefs_enabled",
    )
    _tickers_text = st.text_area(
        ("股票代码 / 公司名（每行一个）"
         if _is_zh else "Tickers / company names (one per line)"),
        value="\n".join(_prefs.get("tickers") or []),
        height=100,
        placeholder="NVDA\n苹果\n贵州茅台",
        key="prefs_tickers",
    )
    _chat_id = st.text_input(
        "Telegram chat_id",
        value=_prefs.get("telegram_chat_id") or "",
        placeholder="123456789",
        key="prefs_chat_id",
    ).strip()
    st.caption(
        ("到 Telegram 找 [@userinfobot](https://t.me/userinfobot) 发 `/start`，"
         "复制它返回的数字 ID 粘到这里。然后给我们的 bot 发一次 `/start` 让它能 DM 你。"
         if _is_zh else
         "On Telegram, message [@userinfobot](https://t.me/userinfobot) with "
         "`/start` and paste the numeric ID it returns here. Also send `/start` "
         "to the project bot so it's allowed to DM you.")
    )

    _col_save, _col_test = st.columns(2)
    if _col_save.button(("💾 保存" if _is_zh else "💾 Save"),
                        use_container_width=True, key="prefs_save"):
        new_prefs = dict(_prefs)
        new_prefs["daily_schedule_enabled"] = bool(_enable)
        new_prefs["tickers"] = [
            line.strip() for line in (_tickers_text or "").splitlines()
            if line.strip()
        ]
        new_prefs["telegram_chat_id"] = _chat_id
        # Snapshot the user's current model/analysts/lang choices so the
        # scheduled run uses the same setup as their last manual config.
        new_prefs["selected_analysts"] = selected_analysts
        new_prefs["provider"] = provider
        new_prefs["deep_model"] = deep_model
        new_prefs["quick_model"] = quick_model
        new_prefs["output_language"] = output_language
        new_prefs["max_debate_rounds"] = debate_rounds
        new_prefs["max_risk_discuss_rounds"] = risk_rounds
        user_prefs.save(_authed_email, new_prefs)
        st.success("✓ saved" if not _is_zh else "✓ 已保存")

    if _col_test.button(("🧪 测试推送" if _is_zh else "🧪 Test send"),
                       use_container_width=True, key="prefs_test"):
        if not _chat_id:
            st.error("Need a chat_id first.")
        elif not os.getenv("TELEGRAM_BOT_TOKEN"):
            st.error("Server is missing TELEGRAM_BOT_TOKEN in .env")
        else:
            ok, detail = notify.send_telegram(
                _chat_id,
                ("✅ TradingAgents test message — your daily reports will arrive here."
                 if not _is_zh else
                 "✅ TradingAgents 测试消息 — 每日报告会发送到这里。"),
            )
            if ok:
                st.success("✓ sent — check your Telegram")
            else:
                st.error(f"send failed: {detail}")

# A slot we can swap with a "Running…" indicator once the analysis starts.
_run_btn_slot = st.sidebar.empty()
run = _run_btn_slot.button(
    T("run_btn"), type="primary", use_container_width=True,
    disabled=not (key_present and selected_analysts and ticker),
    key="run_btn",
)

# ════════════════════════════════════════════════════════════════════
# Main area
# ════════════════════════════════════════════════════════════════════
st.title(T("page_title").format(ticker or "—", trade_date))
st.caption(
    T("page_caption").format(
        provider, deep_model, quick_model, ", ".join(selected_analysts) or "none"
    )
)

if ticker:
    _render_range_stats_card(ticker, str(trade_date))

if resolution_msg and resolution_msg != f"{raw_input} → {ticker}":
    st.caption(f"🔍 {resolution_msg}")

# ─── Resume-or-spawn worker ───
# A worker subprocess survives Streamlit script reruns: it lives in the
# process-global ``_state["runs"]`` registry, keyed by a run-id stored in
# ``st.session_state``. Any sidebar widget interaction (e.g. switching
# language) re-runs the script, but we re-attach to the same worker rather
# than aborting it.
_sem = _run_semaphore()
_state = _running_state()


def _release_slot(run_id):
    """Idempotent: drop the registry entry + release the semaphore."""
    if _state["runs"].pop(run_id, None) is not None:
        try:
            _sem.release()
        except ValueError:
            pass


# Garbage-collect any registry entries whose subprocess has exited but whose
# session disappeared (e.g. user closed the browser mid-run). Without this,
# the semaphore would slowly leak.
for _rid, _info in list(_state["runs"].items()):
    _proc = _info.get("proc")
    if _proc is not None and _proc.poll() is not None:
        if _info.get("decision") is None and _info.get("error") is None:
            # Worker exited but never emitted "done" — surface as error
            _info["error"] = {"type": "WorkerExited",
                              "msg": f"worker exited with code {_proc.returncode}"}
        # Only auto-release if no session is still tracking this run
        if _info.get("session_count", 0) <= 0:
            _release_slot(_rid)

current_run_id = st.session_state.get("current_run_id")
worker_info = _state["runs"].get(current_run_id) if current_run_id else None

# Show "other in-flight runs" in sidebar
_other_runs = [
    (rid, info) for rid, info in _state["runs"].items() if rid != current_run_id
]
if _other_runs:
    with st.sidebar.expander(
        f"🟡 {len(_other_runs)} other run(s) in flight", expanded=False
    ):
        for rid, info in _other_runs:
            elapsed = int(time.time() - info["started_at"])
            st.markdown(f"• {info['email']} → **{info['ticker']}** ({elapsed}s)")

# Idle path: no in-flight worker for this session, and user didn't click Run
if not run and worker_info is None:
    st.info(T("intro"))
    _hist_log = TradingMemoryLog({"memory_log_path": USER_MEMORY_PATH})
    _entries = list(reversed(_hist_log.load_entries()))
    _hist_title = "📜 我的历史" if st.session_state["ui_lang"] == "zh" else "📜 My history"
    import json as _hist_json
    _is_zh = st.session_state["ui_lang"] == "zh"
    _full_log_dir = Path(USER_RESULTS_DIR)

    def _load_full_state(ticker: str, date: str) -> dict | None:
        """Read the per-run full state JSON if present (all analyst reports etc.)."""
        p = _full_log_dir / ticker / "TradingAgentsStrategy_logs" / f"full_states_log_{date}.json"
        if not p.exists():
            return None
        try:
            return _hist_json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None

    _section_order_zh = [
        ("market_report", "📊 市场分析"),
        ("sentiment_report", "💬 情绪分析"),
        ("news_report", "📰 新闻分析"),
        ("fundamentals_report", "🏢 基本面分析"),
        ("investment_plan", "⚖️ 投资方案（研究经理）"),
        ("trader_investment_decision", "💼 交易员方案"),
        ("final_trade_decision", "🧑‍💼 最终决策（投资组合经理）"),
    ]
    _section_order_en = [
        ("market_report", "📊 Market"),
        ("sentiment_report", "💬 Sentiment"),
        ("news_report", "📰 News"),
        ("fundamentals_report", "🏢 Fundamentals"),
        ("investment_plan", "⚖️ Investment Plan (Research Manager)"),
        ("trader_investment_decision", "💼 Trader Plan"),
        ("final_trade_decision", "🧑‍💼 Final Decision (Portfolio Manager)"),
    ]
    _section_order = _section_order_zh if _is_zh else _section_order_en


    with st.expander(f"{_hist_title} ({len(_entries)})", expanded=bool(_entries)):
        if not _entries:
            st.caption("—" if not _is_zh else "暂无历史")
        else:
            for _idx, e in enumerate(_entries[:50]):
                tag = f"`{e['date']}` **{e['ticker']}** · {e['rating']}"
                if e.get("alpha"):
                    tag += f" · α={e['alpha']}"
                if e.get("pending"):
                    tag += " · ⏳ pending"
                # Auto-expand the most recent entry so users see content immediately.
                with st.expander(tag, expanded=(_idx == 0)):
                    full = _load_full_state(e["ticker"], e["date"])

                    if full:
                        # Use tabs (Streamlit allows tabs inside an expander; expanders
                        # inside expanders render flaky on the frontend).
                        all_sections: list[tuple[str, str]] = []
                        for key, label in _section_order:
                            content = full.get(key) or ""
                            if isinstance(content, str) and content.strip():
                                all_sections.append((label, content))

                        debate = full.get("investment_debate_state") or {}
                        bull = (debate.get("bull_history") or "").strip()
                        bear = (debate.get("bear_history") or "").strip()
                        rj = (debate.get("judge_decision") or "").strip()
                        if bull or bear or rj:
                            md_parts = []
                            if bull: md_parts.append(f"### 🐂 Bull\n{bull}")
                            if bear: md_parts.append(f"### 🐻 Bear\n{bear}")
                            if rj:
                                rm = "### ⚖️ 研究经理判决" if _is_zh else "### ⚖️ Research Manager"
                                md_parts.append(f"{rm}\n{rj}")
                            label = "🐂🐻 多空辩论" if _is_zh else "🐂🐻 Bull/Bear Debate"
                            all_sections.append((label, "\n\n".join(md_parts)))

                        risk = full.get("risk_debate_state") or {}
                        agg = (risk.get("aggressive_history") or "").strip()
                        con = (risk.get("conservative_history") or "").strip()
                        neu = (risk.get("neutral_history") or "").strip()
                        rrj = (risk.get("judge_decision") or "").strip()
                        if agg or con or neu or rrj:
                            md_parts = []
                            if agg: md_parts.append(f"### 🔥 Aggressive\n{agg}")
                            if con: md_parts.append(f"### 🛡️ Conservative\n{con}")
                            if neu: md_parts.append(f"### ⚖️ Neutral\n{neu}")
                            if rrj:
                                pm = "### 🧑‍💼 投资组合经理" if _is_zh else "### 🧑‍💼 Portfolio Manager"
                                md_parts.append(f"{pm}\n{rrj}")
                            label = "🔥🛡️ 风险辩论" if _is_zh else "🔥🛡️ Risk Debate"
                            all_sections.append((label, "\n\n".join(md_parts)))

                        if all_sections:
                            tab_objs = st.tabs([s[0] for s in all_sections])
                            for tab, (_, content) in zip(tab_objs, all_sections):
                                tab.markdown(content)
                    else:
                        # Fallback: only the lean memory log was available
                        if e.get("decision"):
                            st.markdown("**Decision**"); st.markdown(e["decision"])

                    if e.get("reflection"):
                        st.markdown("---")
                        rl = "**反思**" if _is_zh else "**Reflection**"
                        st.markdown(rl); st.markdown(e["reflection"])
    st.stop()

# Replace the "Run analysis" button with a disabled "Running…" indicator
_run_btn_slot.button(
    "🔄 Running… / 分析中…", use_container_width=True, disabled=True,
    key="run_btn_disabled",
)

# Spawn a fresh worker if the user just clicked Run and there's no in-flight one
if run and worker_info is None:
    if not _sem.acquire(blocking=False):
        cap = int(os.getenv("MAX_CONCURRENT_RUNS", "4"))
        if st.session_state["ui_lang"] == "zh":
            st.error(f"⏳ 服务器并发上限（{cap}）已满，请稍后再点 ▶ 开始分析。")
        else:
            st.error(f"⏳ Server is at capacity ({cap} runs already active). "
                     f"Please retry in a few minutes.")
        st.stop()

    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = provider
    config["deep_think_llm"] = deep_model
    config["quick_think_llm"] = quick_model
    config["max_debate_rounds"] = debate_rounds
    config["max_risk_discuss_rounds"] = risk_rounds
    config["output_language"] = output_language
    config["backend_url"] = None
    config["checkpoint_enabled"] = checkpoint_enabled
    config["data_cache_dir"] = USER_CACHE_DIR
    config["results_dir"] = USER_RESULTS_DIR
    config["memory_log_path"] = USER_MEMORY_PATH

    import subprocess as _sp_init
    import json as _json_init

    _WORKER_PATH_INIT = str(_ROOT / "worker.py")
    _PYTHON_BIN = os.getenv("TRADINGAGENTS_PYTHON_BIN", sys.executable)
    _proc_new = _sp_init.Popen(
        [_PYTHON_BIN, "-u", _WORKER_PATH_INIT],
        stdin=_sp_init.PIPE, stdout=_sp_init.PIPE, stderr=_sp_init.PIPE,
        text=True, bufsize=1, encoding="utf-8",
    )

    def _assemble_user_research(ticker_: str) -> str:
        chunks = []
        for m in list_research(USER_HOME, ticker_):
            if st.session_state.get(f"ur_{ticker_}_{m['hash']}_chk", True):
                chunks.append(
                    f"## {m['filename']} (uploaded {m['uploaded_at'][:10]})\n{m['summary']}"
                )
        for m in st.session_state.get("ur_per_run", []):
            chunks.append(f"## {m['filename']} (this run)\n{m['summary']}")
        return "\n\n---\n\n".join(chunks)

    user_research_text = _assemble_user_research(ticker) if ticker else ""

    _proc_new.stdin.write(_json_init.dumps({
        "config": config, "ticker": ticker, "trade_date": str(trade_date),
        "selected_analysts": selected_analysts,
        "user_research": user_research_text,
    }))
    _proc_new.stdin.close()

    new_run_id = f"{_authed_email}|{ticker}|{trade_date}|{int(time.time() * 1000)}"
    worker_info = {
        "email": _authed_email, "ticker": ticker, "trade_date": str(trade_date),
        "proc": _proc_new, "started_at": time.time(),
        "chunks": [], "decision": None, "error": None,
        "selected_analysts": selected_analysts,
        "checkpoint_enabled": checkpoint_enabled,
        "session_count": 1,
    }
    _state["runs"][new_run_id] = worker_info
    st.session_state["current_run_id"] = new_run_id
    current_run_id = new_run_id
    print(f"[run] spawned worker pid={_proc_new.pid} for user={_authed_email} "
          f"ticker={ticker} date={trade_date} run_id={new_run_id}", flush=True)

# ───── Header status row ─────
header_col1, header_col2 = st.columns([1, 3])
with header_col1:
    timer_box = st.empty()
with header_col2:
    last_event_box = st.empty()

agent_states = {
    T("agent_market"): "pending", T("agent_social"): "pending",
    T("agent_news"): "pending", T("agent_fundamentals"): "pending",
    T("agent_bull"): "pending", T("agent_bear"): "pending",
    T("agent_research_mgr"): "pending", T("agent_trader"): "pending",
    T("agent_risk_agg"): "pending", T("agent_risk_con"): "pending",
    T("agent_risk_neu"): "pending", T("agent_pm"): "pending",
}
status_box = st.empty()


def render_status():
    rows = " · ".join(f"{_status_dot(s)} {n}" for n, s in agent_states.items())
    status_box.markdown(f"**{T('pipeline_label')}** {rows}")


render_status()

decision_box = st.empty()

tab_titles = [
    T("tab_market"), T("tab_sentiment"), T("tab_news"), T("tab_fundamentals"),
    T("tab_invest"), T("tab_trader"), T("tab_risk"), T("tab_log"),
]
tabs = st.tabs(tab_titles)
placeholders = {
    "market_report": tabs[0].empty(),
    "sentiment_report": tabs[1].empty(),
    "news_report": tabs[2].empty(),
    "fundamentals_report": tabs[3].empty(),
    "investment_plan": tabs[4].empty(),
    "trader_investment_plan": tabs[5].empty(),
    "final_trade_decision": tabs[6].empty(),
}
log_box = tabs[7].empty()
for ph in placeholders.values():
    ph.markdown(T("waiting"))
log_box.markdown(T("waiting"))

events = deque(maxlen=12)
investment_plan_md, risk_plan_md = [], []
start_ts = time.time()

ANALYST_TO_STATUS = {
    "market_report": T("agent_market"), "sentiment_report": T("agent_social"),
    "news_report": T("agent_news"), "fundamentals_report": T("agent_fundamentals"),
}


def push_event(label: str, detail: str = ""):
    ts = time.strftime("%H:%M:%S")
    events.appendleft(f"`{ts}` **{label}**" + (f" — {detail[:120]}" if detail else ""))
    last_event_box.markdown(events[0])
    log_box.markdown("\n\n".join(events))


def tick_timer():
    timer_box.metric(T("elapsed"), f"{int(time.time() - start_ts)}s")


def render_chunk(chunk: dict):
    """Apply one projected chunk dict from the worker to the live UI."""
    for key, status_name in ANALYST_TO_STATUS.items():
        content = chunk.get(key)
        if content:
            placeholders[key].markdown(content)
            if agent_states[status_name] != "completed":
                agent_states[status_name] = "completed"
                push_event(T("ev_analyst_done").format(status_name), content[:200])
                render_status()

    debate = chunk.get("investment_debate_state")
    if debate:
        bull = (debate.get("bull_history") or "").strip()
        bear = (debate.get("bear_history") or "").strip()
        judge = (debate.get("judge_decision") or "").strip()
        new_md = []
        if bull:
            new_md.append(f"### {T('sec_bull')}\n{bull}")
            if agent_states[T("agent_bull")] != "completed":
                agent_states[T("agent_bull")] = "in_progress"
        if bear:
            new_md.append(f"### {T('sec_bear')}\n{bear}")
            if agent_states[T("agent_bear")] != "completed":
                agent_states[T("agent_bear")] = "in_progress"
        if judge:
            new_md.append(f"### {T('sec_research_mgr')}\n{judge}")
            agent_states[T("agent_bull")] = "completed"
            agent_states[T("agent_bear")] = "completed"
            agent_states[T("agent_research_mgr")] = "completed"
        if new_md and new_md != render_chunk._invest_md:
            render_chunk._invest_md = new_md
            placeholders["investment_plan"].markdown("\n\n".join(new_md))
            push_event(T("ev_invest_update"), judge or bear or bull)
            render_status()

    trader = chunk.get("trader_investment_plan")
    if trader and agent_states[T("agent_trader")] != "completed":
        placeholders["trader_investment_plan"].markdown(trader)
        agent_states[T("agent_trader")] = "completed"
        push_event(T("ev_trader_ready"), trader[:200])
        render_status()

    risk = chunk.get("risk_debate_state")
    if risk:
        agg = (risk.get("aggressive_history") or "").strip()
        con = (risk.get("conservative_history") or "").strip()
        neu = (risk.get("neutral_history") or "").strip()
        judge = (risk.get("judge_decision") or "").strip()
        new_md = []
        if agg:
            new_md.append(f"### {T('sec_risk_agg')}\n{agg}")
            if agent_states[T("agent_risk_agg")] != "completed":
                agent_states[T("agent_risk_agg")] = "in_progress"
        if con:
            new_md.append(f"### {T('sec_risk_con')}\n{con}")
            if agent_states[T("agent_risk_con")] != "completed":
                agent_states[T("agent_risk_con")] = "in_progress"
        if neu:
            new_md.append(f"### {T('sec_risk_neu')}\n{neu}")
            if agent_states[T("agent_risk_neu")] != "completed":
                agent_states[T("agent_risk_neu")] = "in_progress"
        if judge:
            new_md.append(f"### {T('sec_pm')}\n{judge}")
            for k in (T("agent_risk_agg"), T("agent_risk_con"),
                      T("agent_risk_neu"), T("agent_pm")):
                agent_states[k] = "completed"
        if new_md and new_md != render_chunk._risk_md:
            render_chunk._risk_md = new_md
            placeholders["final_trade_decision"].markdown("\n\n".join(new_md))
            push_event(T("ev_risk_update"), judge or neu or con or agg)
            render_status()

    ftd = chunk.get("final_trade_decision")
    if ftd:
        live_label = _decision_label(ftd)
        decision_box.markdown(
            f"""
            <div style="background:{_decision_color(live_label)};padding:1.25rem;border-radius:0.75rem;
                        color:white;text-align:center;margin:0.5rem 0;">
                <div style="font-size:0.85rem;opacity:0.85;">{T('decision_live')}</div>
                <div style="font-size:2.5rem;font-weight:700;letter-spacing:0.1em;">{live_label}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# Function-attribute state so render_chunk doesn't reach into outer scope mutables.
render_chunk._invest_md = []
render_chunk._risk_md = []

# Anchor the timer to the worker's start, not this script-rerun.
start_ts = worker_info["started_at"]

if checkpoint_enabled and _existing_step is not None:
    push_event(T("ev_resuming"), T("ev_resuming_d").format(_existing_step, ticker, trade_date))
else:
    push_event(T("ev_started"), T("ev_started_d").format(ticker, trade_date))
tick_timer()

# ─── Replay any chunks already received in prior reruns ───
for _ch in worker_info["chunks"]:
    render_chunk(_ch)

# ─── Continue streaming from the persistent proc ───
import select as _select
import json as _json

_proc = worker_info["proc"]
_stdout_fd = _proc.stdout.fileno()
last_chunk_at = time.time()
try:
    while worker_info["decision"] is None and worker_info["error"] is None:
        if _proc.poll() is not None:
            # Worker exited — drain remaining lines from the pipe before exiting loop.
            for _line in _proc.stdout:
                _line = _line.strip()
                if not _line:
                    continue
                try:
                    ev = _json.loads(_line)
                except _json.JSONDecodeError:
                    print(f"[worker non-JSON] {_line[:200]}", flush=True)
                    continue
                kind = ev.get("kind")
                if kind == "chunk":
                    worker_info["chunks"].append(ev.get("data", {}))
                    render_chunk(ev.get("data", {}))
                elif kind == "done":
                    worker_info["decision"] = ev.get("decision", "")
                elif kind == "error":
                    worker_info["error"] = ev
            break

        ready, _, _ = _select.select([_stdout_fd], [], [], 1.0)
        tick_timer()
        idle_sec = int(time.time() - last_chunk_at)
        if idle_sec >= 5:
            last_event_box.markdown(
                f"⏳ waiting on worker · {idle_sec}s since last chunk"
                if st.session_state["ui_lang"] == "en"
                else f"⏳ 等 worker 中 · 距上次更新 {idle_sec}s"
            )
        if not ready:
            continue

        line = _proc.stdout.readline()
        if not line:  # EOF
            break
        line = line.strip()
        if not line:
            continue
        try:
            ev = _json.loads(line)
        except _json.JSONDecodeError:
            print(f"[worker non-JSON] {line[:200]}", flush=True)
            continue
        kind = ev.get("kind")
        last_chunk_at = time.time()
        if kind == "chunk":
            worker_info["chunks"].append(ev.get("data", {}))
            render_chunk(ev.get("data", {}))
        elif kind == "started":
            push_event(T("ev_started"), T("ev_started_d").format(ticker, trade_date))
        elif kind == "done":
            worker_info["decision"] = ev.get("decision", "")
            print(f"[run] DONE chunks={len(worker_info['chunks'])} "
                  f"decision_len={len(worker_info['decision'])}", flush=True)
        elif kind == "error":
            worker_info["error"] = ev
            print(f"[run] worker ERROR {ev.get('type')}: {ev.get('msg')}", flush=True)
            print(ev.get("trace", ""), flush=True)
finally:
    # Only release / clean up if the worker actually finished. If we were
    # interrupted by a script rerun (e.g. user changed language), leave the
    # registry entry so the next rerun resumes from where we left off.
    if worker_info["decision"] is not None or worker_info["error"] is not None:
        try:
            _proc.wait(timeout=5)
        except Exception:
            pass
        try:
            _stderr_tail = _proc.stderr.read()
            if _stderr_tail:
                for ln in _stderr_tail.splitlines()[-50:]:
                    print(f"[worker stderr] {ln}", flush=True)
        except Exception:
            pass
        _release_slot(current_run_id)
        st.session_state.pop("current_run_id", None)

worker_error = worker_info.get("error")
decision = worker_info.get("decision")

if worker_error:
    push_event(T("ev_error"), worker_error.get("msg", ""))
    st.error(f"{worker_error.get('type', 'Error')}: {worker_error.get('msg', '')}")
    with st.expander("Traceback"):
        st.code(worker_error.get("trace", "(no trace)"), language="text")
    if worker_error.get("checkpoint_preserved"):
        st.warning(T("checkpoint_preserved").format(ticker, trade_date))
    st.stop()

if decision is None:
    # Run is mid-flight (this rerun got interrupted before the worker finished).
    # The streaming loop above already exited because the script is being torn
    # down by Streamlit. Just stop here; the next rerun will resume rendering.
    st.stop()

tick_timer()

try:
    clear_run_dir(USER_HOME, st.session_state["ur_run_id"])
except Exception as e:  # noqa: BLE001
    print(f"[run] clear_run_dir failed: {e}", flush=True)
st.session_state["ur_per_run"] = []
st.session_state["ur_seen_digests"] = set()
st.session_state["ur_run_id"] = f"run-{int(time.time())}-{os.getpid()}"

label = _decision_label(decision)
decision_box.markdown(
    f"""
    <div style="background:{_decision_color(label)};padding:1.5rem;border-radius:0.75rem;
                color:white;text-align:center;margin:1rem 0;">
        <div style="font-size:0.9rem;opacity:0.85;">{T('decision_final')}</div>
        <div style="font-size:3rem;font-weight:700;letter-spacing:0.1em;">{label}</div>
        <div style="font-size:0.85rem;opacity:0.85;margin-top:0.5rem;">
            {T('elapsed_s').format(int(time.time() - start_ts))}
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

push_event(T("ev_complete"), decision[:200] if decision else "")

with st.expander(T("raw_decision")):
    st.code(decision or "(empty)", language="markdown")
