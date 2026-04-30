"""Streamlit web console for TradingAgents."""

from __future__ import annotations

import datetime as dt
import html
import os
from pathlib import Path
from typing import Optional

import streamlit as st

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients.model_catalog import get_model_options
from tradingagents.web.i18n import LANGUAGE_NAMES, LANGUAGE_OPTIONS, t
from tradingagents.web.models import ANALYST_LABELS, ANALYST_ORDER, AnalysisRequest, JobStatus
from tradingagents.web.preferences import latest_request, recent_requests, remember_request
from tradingagents.web.runner import API_KEY_ENV_BY_PROVIDER, AnalysisJobManager, list_saved_reports


PROVIDERS = [
    ("OpenAI", "openai", "https://api.openai.com/v1"),
    ("Google", "google", None),
    ("Anthropic", "anthropic", "https://api.anthropic.com/"),
    ("xAI", "xai", "https://api.x.ai/v1"),
    ("DeepSeek", "deepseek", "https://api.deepseek.com"),
    ("Qwen", "qwen", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    ("GLM", "glm", "https://open.bigmodel.cn/api/paas/v4/"),
    ("OpenRouter", "openrouter", "https://openrouter.ai/api/v1"),
    ("Azure OpenAI", "azure", None),
    ("Ollama", "ollama", "http://localhost:11434/v1"),
]

GEMINI_THINKING_OPTIONS = ["minimal", "high"]
REASONING_EFFORT_OPTIONS = ["low", "medium", "high"]
ANTHROPIC_EFFORT_OPTIONS = ["low", "medium", "high"]
DEEPSEEK_THINKING_OPTIONS = ["disabled", "enabled"]

DEPTH_OPTIONS = [
    ("shallow_depth", 1),
    ("medium_depth", 3),
    ("deep_depth", 5),
]

PIPELINE_GROUPS = [
    ("analyst_team", ["Market Analyst", "Social Analyst", "News Analyst", "Fundamentals Analyst"]),
    ("research_team", ["Bull Researcher", "Bear Researcher", "Research Manager"]),
    ("trading_team", ["Trader"]),
    ("risk_team", ["Aggressive Analyst", "Neutral Analyst", "Conservative Analyst"]),
    ("portfolio_team", ["Portfolio Manager"]),
]


@st.cache_resource
def get_job_manager() -> AnalysisJobManager:
    return AnalysisJobManager()


def _language() -> str:
    return st.session_state.get("interface_language", "English")


def _status_label(language: str, status: str) -> str:
    return t(language, status)


def _provider_label(provider: str) -> str:
    for label, key, _ in PROVIDERS:
        if key == provider:
            return label
    return PROVIDERS[0][0]


def _request_model_label(provider: str, mode: str, model_id: str) -> str:
    if provider in {"azure", "openrouter"}:
        return model_id
    for label, value in get_model_options(provider, mode):
        if value == model_id:
            return label
    return "Custom model ID"


def _request_depth_key(depth: int) -> str:
    for key, value in DEPTH_OPTIONS:
        if value == depth:
            return key
    return DEPTH_OPTIONS[0][0]


def _safe_index(options: list[str], value: Optional[str], default: int = 0) -> int:
    if value in options:
        return options.index(value)
    return default


def _cached_request() -> Optional[AnalysisRequest]:
    cached = st.session_state.get("loaded_request")
    if isinstance(cached, AnalysisRequest):
        return cached
    latest = latest_request()
    if latest:
        st.session_state["loaded_request"] = latest
    return latest


def _recent_label(request: AnalysisRequest) -> str:
    return (
        f"{request.ticker} · {request.llm_provider} · "
        f"{request.quick_think_llm}/{request.deep_think_llm}"
    )


def _inject_css() -> None:
    st.markdown(
        """
        <style>
        :root {
          --ta-ink: #18201f;
          --ta-muted: #687471;
          --ta-line: #d7ded8;
          --ta-panel: #f7f8f4;
          --ta-field: #edf1ec;
          --ta-green: #0f8f6d;
          --ta-amber: #b56b00;
          --ta-red: #b33b3b;
          --ta-blue: #315d8f;
        }
        .stApp {
          background:
            linear-gradient(90deg, rgba(24,32,31,.045) 1px, transparent 1px),
            linear-gradient(rgba(24,32,31,.035) 1px, transparent 1px),
            #fafaf5;
          background-size: 28px 28px;
          color: var(--ta-ink);
        }
        h1, h2, h3 { letter-spacing: 0; }
        .block-container { padding-top: 1.6rem; max-width: 1500px; }
        section[data-testid="stSidebar"] {
          background: #eef2ed;
          border-right: 1px solid var(--ta-line);
        }
        .ta-title {
          border-bottom: 2px solid var(--ta-ink);
          padding-bottom: .7rem;
          margin-bottom: 1rem;
        }
        .ta-title h1 {
          font-size: 2rem;
          line-height: 1.08;
          margin: 0;
        }
        .ta-title p {
          margin: .35rem 0 0;
          color: var(--ta-muted);
          font-size: .94rem;
        }
        .ta-card {
          background: rgba(247,248,244,.94);
          border: 1px solid var(--ta-line);
          border-radius: 6px;
          padding: .9rem;
          box-shadow: 0 1px 0 rgba(24,32,31,.05);
        }
        .ta-pipeline {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(155px, 1fr));
          gap: .55rem;
          margin: .4rem 0 1rem;
        }
        .ta-agent {
          min-height: 74px;
          border: 1px solid var(--ta-line);
          border-left: 5px solid #9aa5a0;
          border-radius: 5px;
          background: #ffffffd9;
          padding: .62rem .68rem;
        }
        .ta-agent strong {
          display: block;
          font-size: .86rem;
          line-height: 1.18;
          margin-bottom: .35rem;
        }
        .ta-agent span {
          display: inline-block;
          font-size: .72rem;
          text-transform: uppercase;
          letter-spacing: .04em;
          color: var(--ta-muted);
        }
        .ta-status-in_progress { border-left-color: var(--ta-amber); }
        .ta-status-completed { border-left-color: var(--ta-green); }
        .ta-status-failed { border-left-color: var(--ta-red); }
        .ta-status-running { color: var(--ta-amber); }
        .ta-status-completed-text { color: var(--ta-green); }
        .ta-status-failed-text { color: var(--ta-red); }
        .ta-message {
          border-left: 3px solid var(--ta-blue);
          padding: .45rem .7rem;
          margin-bottom: .45rem;
          background: #fffdfa;
        }
        .ta-message small { color: var(--ta-muted); }
        .ta-token-metric {
          min-height: 72px;
          display: flex;
          flex-direction: column;
          justify-content: center;
          gap: .18rem;
        }
        .ta-token-label {
          color: var(--ta-muted);
          font-size: .85rem;
          font-weight: 600;
        }
        .ta-token-metric span {
          color: var(--ta-muted);
          display: inline-block;
          min-width: 3.9rem;
        }
        .ta-token-metric strong {
          color: var(--ta-ink);
          font-size: 1.12rem;
          font-weight: 700;
        }
        div.stButton > button[kind="primary"],
        button[data-testid="stBaseButton-primary"] {
          background: var(--ta-ink);
          border-color: var(--ta-ink);
          color: white;
        }
        div.stButton > button[kind="primary"]:hover,
        button[data-testid="stBaseButton-primary"]:hover {
          background: var(--ta-green);
          border-color: var(--ta-green);
          color: white;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _model_selector(
    provider: str,
    mode: str,
    language: str,
    cached: Optional[AnalysisRequest] = None,
) -> str:
    cached_model = None
    if cached and cached.llm_provider == provider:
        cached_model = cached.quick_think_llm if mode == "quick" else cached.deep_think_llm

    if provider == "azure":
        return st.text_input(
            t(language, f"{mode}_deployment"),
            value=cached_model or "",
            key=f"{mode}-azure-model",
        ).strip()
    if provider == "openrouter":
        return st.text_input(
            t(language, f"{mode}_openrouter"),
            value=cached_model or ("openai/gpt-5.4-mini" if mode == "quick" else "openai/gpt-5.4"),
            key=f"{mode}-openrouter-model",
        ).strip()

    options = get_model_options(provider, mode)
    labels = [label for label, _ in options]
    values = {label: value for label, value in options}
    cached_label = _request_model_label(provider, mode, cached_model) if cached_model else labels[0]
    label = st.selectbox(
        t(language, f"{mode}_model"),
        labels,
        index=_safe_index(labels, cached_label),
        key=f"{mode}-{provider}-model",
    )
    if values[label] == "custom":
        return st.text_input(
            t(language, f"custom_{mode}"),
            value=cached_model or "",
            key=f"{mode}-{provider}-custom",
        ).strip()
    return values[label]


def _provider_settings(
    provider: str,
    language: str,
    cached: Optional[AnalysisRequest] = None,
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    google_thinking = None
    openai_effort = None
    anthropic_effort = None
    deepseek_thinking = None

    if provider == "google":
        google_thinking = st.selectbox(
            t(language, "gemini_thinking"),
            GEMINI_THINKING_OPTIONS,
            index=_safe_index(GEMINI_THINKING_OPTIONS, cached.google_thinking_level if cached else "high"),
        )
    elif provider == "openai":
        openai_effort = st.selectbox(
            t(language, "openai_effort"),
            REASONING_EFFORT_OPTIONS,
            index=_safe_index(REASONING_EFFORT_OPTIONS, cached.openai_reasoning_effort if cached else "medium"),
        )
    elif provider == "anthropic":
        anthropic_effort = st.selectbox(
            t(language, "anthropic_effort"),
            ANTHROPIC_EFFORT_OPTIONS,
            index=_safe_index(ANTHROPIC_EFFORT_OPTIONS, cached.anthropic_effort if cached else "high"),
        )
    elif provider == "deepseek":
        deepseek_thinking = st.selectbox(
            t(language, "deepseek_thinking"),
            DEEPSEEK_THINKING_OPTIONS,
            index=_safe_index(DEEPSEEK_THINKING_OPTIONS, cached.deepseek_thinking if cached else "disabled"),
        )

    return google_thinking, openai_effort, anthropic_effort, deepseek_thinking


def _render_api_key_status(provider: str, language: str) -> None:
    env_var = API_KEY_ENV_BY_PROVIDER.get(provider)
    if not env_var:
        st.caption(t(language, "api_key_not_required"))
        return
    if os.environ.get(env_var, "").strip():
        st.success(t(language, "api_key_ready", env_var=env_var))
    else:
        st.warning(t(language, "api_key_missing", env_var=env_var))


def _render_request_form(manager: AnalysisJobManager) -> None:
    language = _language()
    cached = _cached_request()
    provider_labels = [label for label, _, _ in PROVIDERS]
    provider_by_label = {label: (key, url) for label, key, url in PROVIDERS}

    with st.sidebar:
        current_language = st.selectbox(
            t(language, "interface_language"),
            [key for key, _ in LANGUAGE_OPTIONS],
            index=[key for key, _ in LANGUAGE_OPTIONS].index(language),
            format_func=lambda key: LANGUAGE_NAMES[key],
            key="interface_language",
        )
        language = current_language
        recent = recent_requests()
        st.markdown(f"### {t(language, 'recent_setup')}")
        if recent:
            selected_recent = st.selectbox(
                t(language, "recent_setup"),
                recent,
                format_func=_recent_label,
                label_visibility="collapsed",
            )
            if st.button(t(language, "load_recent"), use_container_width=True):
                st.session_state["loaded_request"] = selected_recent
                st.rerun()
        else:
            st.caption(t(language, "recent_setup_empty"))

        cached = _cached_request()
        with st.expander(t(language, "analysis_setup"), expanded=True):
            ticker = st.text_input(
                t(language, "ticker"),
                value=cached.ticker if cached else "SPY",
                help=t(language, "ticker_help"),
            ).strip().upper()
            cached_date = dt.date.today()
            if cached:
                try:
                    cached_date = dt.datetime.strptime(cached.analysis_date, "%Y-%m-%d").date()
                except ValueError:
                    cached_date = dt.date.today()
            analysis_date = st.date_input(
                t(language, "analysis_date"),
                value=min(cached_date, dt.date.today()),
                max_value=dt.date.today(),
            )
            language_keys = [key for key, _ in LANGUAGE_OPTIONS]
            output_language = st.selectbox(
                t(language, "output_language"),
                language_keys,
                index=_safe_index(language_keys, cached.output_language if cached else "English"),
                format_func=lambda key: LANGUAGE_NAMES[key],
            )

            analyst_labels = [ANALYST_LABELS[key] for key in ANALYST_ORDER]
            cached_analysts = cached.normalized_analysts() if cached else ANALYST_ORDER
            selected_labels = st.multiselect(
                t(language, "analysts"),
                analyst_labels,
                default=[ANALYST_LABELS[key] for key in cached_analysts],
            )
            selected_analysts = [
                key for key, label in ANALYST_LABELS.items()
                if label in selected_labels
            ]

            depth_keys = [key for key, _ in DEPTH_OPTIONS]
            depth_key = st.selectbox(
                t(language, "research_depth"),
                depth_keys,
                index=_safe_index(depth_keys, _request_depth_key(cached.research_depth) if cached else depth_keys[0]),
                format_func=lambda key: t(language, key),
            )

        with st.expander(t(language, "model_setup"), expanded=True):
            provider_label = st.selectbox(
                t(language, "llm_provider"),
                provider_labels,
                index=_safe_index(provider_labels, _provider_label(cached.llm_provider) if cached else provider_labels[0]),
            )
            provider, backend_url = provider_by_label[provider_label]
            _render_api_key_status(provider, language)
            quick_model = _model_selector(provider, "quick", language, cached)
            deep_model = _model_selector(provider, "deep", language, cached)
            google_thinking, openai_effort, anthropic_effort, deepseek_thinking = _provider_settings(provider, language, cached)

        with st.expander(t(language, "advanced"), expanded=False):
            checkpoint = st.checkbox(t(language, "checkpoint"), value=cached.checkpoint if cached else False)
        submitted = st.button(t(language, "queue_analysis"), type="primary", use_container_width=True)

        if submitted:
            if not ticker or not selected_analysts or not quick_model or not deep_model:
                st.error(t(language, "required_error"))
            else:
                request = AnalysisRequest(
                    ticker=ticker,
                    analysis_date=analysis_date.strftime("%Y-%m-%d"),
                    output_language=output_language,
                    analysts=selected_analysts,
                    research_depth=dict(DEPTH_OPTIONS)[depth_key],
                    llm_provider=provider,
                    backend_url=backend_url,
                    quick_think_llm=quick_model,
                    deep_think_llm=deep_model,
                    google_thinking_level=google_thinking,
                    openai_reasoning_effort=openai_effort,
                    anthropic_effort=anthropic_effort,
                    deepseek_thinking=deepseek_thinking,
                    checkpoint=checkpoint,
                )
                remember_request(request)
                st.session_state["loaded_request"] = request
                job = manager.enqueue(request)
                st.session_state["selected_job_id"] = job.job_id
                st.success(t(language, "queued_job", job_id=job.job_id))


def _duration(started_at, finished_at) -> str:
    if not started_at:
        return "0s"
    end = finished_at or dt.datetime.now()
    seconds = max(0, int((end - started_at).total_seconds()))
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes}m {seconds}s" if minutes else f"{seconds}s"


def _render_job_queue(manager: AnalysisJobManager, language: str) -> None:
    jobs = manager.list_jobs()
    st.markdown(f"### {t(language, 'job_queue')}")
    if not jobs:
        st.info(t(language, "no_jobs"))
        return

    for job in jobs[:12]:
        view = job.view()
        request = view["request"]
        cols = st.columns([1.1, 1, 1, .9, .7])
        label = f"{request.ticker} · {request.analysis_date}"
        if cols[0].button(label, key=f"select-{view['job_id']}", use_container_width=True):
            st.session_state["selected_job_id"] = view["job_id"]
        cols[1].write(_status_label(language, view["status"]))
        cols[2].write(_duration(view["started_at"], view["finished_at"]))
        cols[3].write(request.llm_provider)
        if view["status"] == JobStatus.QUEUED.value:
            if cols[4].button(t(language, "cancel"), key=f"cancel-{view['job_id']}"):
                manager.cancel(view["job_id"])
                st.rerun()


def _selected_job(manager: AnalysisJobManager):
    jobs = manager.list_jobs()
    if not jobs:
        return None
    selected_id = st.session_state.get("selected_job_id")
    if selected_id:
        selected = manager.get_job(selected_id)
        if selected:
            return selected
    return jobs[0]


def _render_metrics(view: dict, language: str) -> None:
    snapshot = view["snapshot"]
    stats = snapshot.stats or {}
    cols = st.columns(5)
    cols[0].metric(t(language, "status"), _status_label(language, view["status"]))
    cols[1].metric(t(language, "elapsed"), _duration(view["started_at"], view["finished_at"]))
    cols[2].metric(t(language, "llm_calls"), stats.get("llm_calls", 0))
    cols[3].metric(t(language, "tool_calls"), stats.get("tool_calls", 0))
    cols[4].markdown(
        f"""
        <div class="ta-token-metric">
          <div class="ta-token-label">{html.escape(t(language, "tokens"))}</div>
          <div><span>{html.escape(t(language, "token_input"))}</span> <strong>{stats.get('tokens_in', 0):,}</strong></div>
          <div><span>{html.escape(t(language, "token_output"))}</span> <strong>{stats.get('tokens_out', 0):,}</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _stage_status(statuses: list[str]) -> str:
    if not statuses:
        return "pending"
    if any(status == "failed" for status in statuses):
        return "failed"
    if all(status == "completed" for status in statuses):
        return "completed"
    if any(status in {"in_progress", "running"} for status in statuses):
        return "in_progress"
    return "pending"


def _stage_progress(statuses: list[str]) -> float:
    if not statuses:
        return 0.0
    completed = sum(1 for status in statuses if status == "completed")
    if any(status in {"in_progress", "running"} for status in statuses):
        completed += 0.5
    return min(1.0, completed / len(statuses))


def _render_pipeline(snapshot, language: str) -> None:
    st.markdown(f"#### {t(language, 'execution_flow')}")
    cols = st.columns(len(PIPELINE_GROUPS))
    for col, (stage_key, agents) in zip(cols, PIPELINE_GROUPS):
        statuses = [snapshot.agent_status.get(agent, "pending") for agent in agents]
        status = _stage_status(statuses)
        with col:
            with st.container(border=True):
                st.caption(t(language, stage_key))
                st.markdown(f"**{t(language, status)}**")
                st.progress(_stage_progress(statuses), text=f"{statuses.count('completed')}/{len(statuses)}")

    with st.expander(t(language, "agent_details"), expanded=False):
        rows = [
            {"agent": agent, "status": t(language, status)}
            for agent, status in snapshot.agent_status.items()
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_messages(snapshot, language: str) -> None:
    if not snapshot.messages:
        st.info(t(language, "no_messages"))
        return
    for message in snapshot.messages[-80:][::-1]:
        st.markdown(
            f"""
            <div class="ta-message">
              <small>{html.escape(message.timestamp)} · {html.escape(message.message_type)}</small>
              <div>{html.escape(message.content[:1800])}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_reports(snapshot, language: str) -> None:
    sections = {key: value for key, value in snapshot.report_sections.items() if value}
    if not sections:
        st.info(t(language, "reports_empty"))
        return
    for section, content in sections.items():
        with st.expander(section.replace("_", " ").title(), expanded=True):
            st.markdown(content)


def _render_tool_calls(snapshot, language: str) -> None:
    if not snapshot.tool_calls:
        st.info(t(language, "tool_calls_empty"))
        return
    rows = [
        {
            "time": call.timestamp,
            "tool": call.tool_name,
            "args": str(call.args),
        }
        for call in snapshot.tool_calls[::-1]
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_final(snapshot, language: str) -> None:
    if snapshot.decision:
        st.metric(t(language, "final_rating"), snapshot.decision)
    final_text = snapshot.report_sections.get("final_trade_decision")
    if final_text:
        st.markdown(final_text)
    if snapshot.report_path:
        st.caption(t(language, "saved_report", path=snapshot.report_path))
    if not snapshot.decision and not final_text:
        st.info(t(language, "final_empty"))


def _render_decision_summary(snapshot, language: str) -> None:
    final_text = snapshot.report_sections.get("final_trade_decision")
    if not snapshot.decision and not final_text:
        return

    with st.container(border=True):
        st.markdown(f"#### {t(language, 'final_summary')}")
        cols = st.columns([1, 3])
        cols[0].metric(t(language, "final_rating"), str(snapshot.decision or t(language, "pending")))
        if final_text:
            excerpt = " ".join(
                line.strip()
                for line in final_text.splitlines()
                if line.strip() and not line.strip().startswith("#")
            )
            cols[1].write(excerpt[:700] + ("..." if len(excerpt) > 700 else ""))
        if snapshot.report_path:
            st.caption(t(language, "saved_report", path=snapshot.report_path))


def _render_history(language: str) -> None:
    reports = list_saved_reports(DEFAULT_CONFIG["results_dir"])
    if not reports:
        st.info(t(language, "history_empty"))
        return
    labels = [str(path.relative_to(Path(DEFAULT_CONFIG["results_dir"]))) for path in reports]
    selected = st.selectbox(t(language, "saved_reports"), labels)
    report_path = reports[labels.index(selected)]
    st.caption(str(report_path))
    st.markdown(report_path.read_text(encoding="utf-8"))


@st.fragment(run_every="1s")
def _render_live_console(manager: AnalysisJobManager) -> None:
    language = _language()
    _render_job_queue(manager, language)
    job = _selected_job(manager)
    if not job:
        return

    view = job.view()
    snapshot = view["snapshot"]
    request = view["request"]
    st.markdown(f"### {t(language, 'live_analysis')} · `{request.ticker}` · `{request.analysis_date}`")
    if view["error"]:
        st.error(view["error"])
    _render_metrics(view, language)
    _render_decision_summary(snapshot, language)

    messages_tab, reports_tab, tools_tab, final_tab, history_tab = st.tabs(
        [
            t(language, "live_messages"),
            t(language, "reports"),
            t(language, "tool_calls_tab"),
            t(language, "final_decision"),
            t(language, "history"),
        ]
    )
    with messages_tab:
        _render_pipeline(snapshot, language)
        st.divider()
        _render_messages(snapshot, language)
    with reports_tab:
        _render_reports(snapshot, language)
    with tools_tab:
        _render_tool_calls(snapshot, language)
    with final_tab:
        _render_final(snapshot, language)
    with history_tab:
        _render_history(language)


def main() -> None:
    st.set_page_config(page_title="TradingAgents Web Console", layout="wide")
    _inject_css()
    manager = get_job_manager()
    _render_request_form(manager)
    language = _language()

    st.markdown(
        f"""
        <div class="ta-title">
          <h1>{html.escape(t(language, "app_title"))}</h1>
          <p>{html.escape(t(language, "app_subtitle"))}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _render_live_console(manager)


if __name__ == "__main__":
    main()
