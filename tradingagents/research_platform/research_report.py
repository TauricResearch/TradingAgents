"""Markdown report generation for normalized personal research artifacts."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from tradingagents.dataflows.utils import safe_ticker_component

from .agent_artifacts import (
    render_agent_output,
    render_analyst_note,
    render_investment_thesis,
    render_trade_signal,
)
from .agent_contracts import (
    AgentOutputEnvelope,
    AgentOutputSection,
    AnalystNote,
    InvestmentThesis,
    TradeSignal,
)
from .backtest_contracts import BacktestResult
from .company_profile import build_company_profile
from .data_contracts import FundamentalSnapshot, NewsItem, PriceBar
from .data_health import build_cache_data_health
from .financial_health import assess_financial_health
from .research_readiness import build_research_readiness
from .risk_contracts import RiskReview
from .valuation_context import build_valuation_context


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ResearchRunAudit(BaseModel):
    """Safe, reproducible configuration and execution summary for one run."""

    model_config = ConfigDict(frozen=True)

    narrative_mode: str = Field(min_length=1)
    data_provider: str = Field(min_length=1)
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_endpoint: str | None = None
    prompt_versions: list[str] = Field(default_factory=list)
    technical_feature_version: str = Field(min_length=1)
    context_fingerprint: str = Field(min_length=16)
    price_basis: str = Field(min_length=1)
    price_bar_count: int = Field(ge=0)
    adjusted_price_bar_count: int = Field(ge=0)
    successful_model_stages: int = Field(default=0, ge=0)
    degraded_model_stages: int = Field(default=0, ge=0)
    total_model_latency_ms: int = Field(default=0, ge=0)
    usage: dict[str, int | float] = Field(default_factory=dict)


class ResearchReportBundle(BaseModel):
    """All artifacts needed to render one personal ticker research report."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    as_of_date: datetime
    generated_at: datetime = Field(default_factory=_utc_now)
    run_audit: ResearchRunAudit | None = None
    price_bars: list[PriceBar] = Field(default_factory=list)
    fundamentals: list[FundamentalSnapshot] = Field(default_factory=list)
    news: list[NewsItem] = Field(default_factory=list)
    agent_outputs: list[AgentOutputEnvelope] = Field(default_factory=list)
    analyst_notes: list[AnalystNote] = Field(default_factory=list)
    thesis: InvestmentThesis | None = None
    signal: TradeSignal | None = None
    risk_review: RiskReview | None = None
    backtest_result: BacktestResult | None = None


def render_research_report(bundle: ResearchReportBundle) -> str:
    """Render a complete Markdown research report from validated artifacts."""

    sections = [
        _render_header(bundle),
        _render_run_audit(bundle.run_audit),
        _render_market_snapshot(bundle.price_bars),
        _render_company_profile(bundle),
        _render_research_readiness(bundle),
        _render_fundamentals(bundle.fundamentals),
        _render_valuation_context(bundle.fundamentals),
        _render_financial_quality(bundle.fundamentals),
        _render_financial_health(bundle.fundamentals),
        _render_financial_trend(bundle.fundamentals),
        _render_news(bundle.news),
        _render_agent_outputs(bundle.agent_outputs),
        _render_analyst_notes(bundle.analyst_notes),
        _render_thesis(bundle.thesis),
        _render_signal(bundle.signal),
        _render_risk_review(bundle.risk_review),
        _render_backtest(bundle.backtest_result),
        _render_provenance(bundle),
    ]
    return "\n\n".join(section for section in sections if section).rstrip() + "\n"


def write_research_report(bundle: ResearchReportBundle, output_dir: str | Path) -> Path:
    """Write a Markdown report and return its path."""

    safe_symbol = safe_ticker_component(bundle.symbol)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    report_path = output_path / f"{safe_symbol}_{bundle.as_of_date.date().isoformat()}.md"
    report_path.write_text(render_research_report(bundle), encoding="utf-8")
    return report_path


def _render_header(bundle: ResearchReportBundle) -> str:
    return "\n".join(
        [
            f"# Personal Research Report: {bundle.symbol}",
            "",
            f"**As Of:** {bundle.as_of_date.date().isoformat()}",
            f"**Generated:** {bundle.generated_at.isoformat()}",
            "",
            "> This report is generated from validated platform artifacts. "
            "It is research support, not trading advice.",
        ]
    )


def _render_run_audit(audit: ResearchRunAudit | None) -> str:
    if audit is None:
        return ""

    model = (
        f"{audit.llm_provider} / {audit.llm_model}"
        if audit.llm_provider and audit.llm_model
        else "Not used"
    )
    adjustment_coverage = (
        audit.adjusted_price_bar_count / audit.price_bar_count if audit.price_bar_count else 0.0
    )
    usage = (
        ", ".join(f"{key}={value}" for key, value in sorted(audit.usage.items())) or "Unavailable"
    )
    return "\n".join(
        [
            "## Run Audit",
            "",
            "| Mode | Data Provider | Model | Prompt | Technical Version |",
            "| --- | --- | --- | --- | --- |",
            f"| {audit.narrative_mode} | {audit.data_provider} | {model} | "
            f"{', '.join(audit.prompt_versions) or 'Deterministic'} | "
            f"{audit.technical_feature_version} |",
            "",
            f"- **LLM endpoint:** {audit.llm_endpoint or 'Not used'}",
            f"- **Context fingerprint:** {audit.context_fingerprint}",
            f"- **Price basis:** {audit.price_basis}; adjusted coverage "
            f"{adjustment_coverage:.1%} ({audit.adjusted_price_bar_count}/{audit.price_bar_count})",
            f"- **Model stages:** {audit.successful_model_stages} succeeded; "
            f"{audit.degraded_model_stages} degraded; {audit.total_model_latency_ms} ms recorded latency",
            f"- **Usage:** {usage}",
        ]
    )


def _render_market_snapshot(price_bars: list[PriceBar]) -> str:
    if not price_bars:
        return "## Market Snapshot\n\nNo normalized price bars available."

    ordered = sorted(price_bars, key=lambda bar: bar.date)
    first = ordered[0]
    last = ordered[-1]
    first_value = first.adjusted_close if first.adjusted_close is not None else first.close
    last_value = last.adjusted_close if last.adjusted_close is not None else last.close
    change = last_value / first_value - 1.0 if first_value else 0.0
    adjusted_count = sum(bar.adjusted_close is not None for bar in ordered)
    price_basis = (
        "forward-adjusted"
        if adjusted_count == len(ordered)
        else "mixed"
        if adjusted_count
        else "raw"
    )
    adjustment_coverage = adjusted_count / len(ordered)
    return "\n".join(
        [
            "## Market Snapshot",
            "",
            "| Start | End | Analysis Close | Range Change | Bars | Price Basis | Adjusted Coverage |",
            "| --- | --- | ---: | ---: | ---: | --- | ---: |",
            "| "
            + " | ".join(
                [
                    first.date.isoformat(),
                    last.date.isoformat(),
                    _money(last_value, last.currency),
                    _pct(change),
                    str(len(ordered)),
                    price_basis,
                    _pct(adjustment_coverage),
                ]
            )
            + " |",
        ]
    )


def _render_company_profile(bundle: ResearchReportBundle) -> str:
    profile = build_company_profile(bundle.fundamentals, symbol=bundle.symbol)
    if not profile.available:
        return "## Company Profile\n\nNo vendor-supplied company profile is available."
    rows = [
        f"| {label} | {value} |"
        for label, value in (
            ("Name", profile.name),
            ("Area", profile.area),
            ("Industry", profile.industry),
            ("Market", profile.market),
            ("Exchange", profile.exchange),
            ("Listing Date", profile.list_date),
        )
        if value is not None
    ]
    return "\n".join(
        [
            "## Company Profile",
            "",
            f"**Available As Of:** {profile.as_of_date}",
            "",
            "| Field | Value |",
            "| --- | --- |",
            *rows,
        ]
    )


def _render_research_readiness(bundle: ResearchReportBundle) -> str:
    financial_snapshots = [
        item
        for item in bundle.fundamentals
        if item.fiscal_period is not None and item.fiscal_period.startswith("financial_report_")
    ]
    latest_financial = (
        max(financial_snapshots, key=lambda item: (item.provenance.as_of_date, item.period_end))
        if financial_snapshots
        else None
    )
    readiness = build_research_readiness(
        data_health=build_cache_data_health(
            price_bars=bundle.price_bars,
            fundamentals=bundle.fundamentals,
            news=bundle.news,
            reference_as_of_date=bundle.as_of_date.date(),
        ),
        valuation_context=build_valuation_context(bundle.fundamentals),
        financial_health=assess_financial_health(latest_financial),
        agent_outputs=bundle.agent_outputs,
        signal=bundle.signal,
        risk_review=bundle.risk_review,
        backtest_result=bundle.backtest_result,
    )
    rows = [
        f"| {item.label} | {item.status.value} | {'required' if item.required else 'optional'} | {item.detail} |"
        for item in readiness.items
    ]
    return "\n".join(
        [
            "## Research Readiness",
            "",
            f"**Status:** {readiness.status.value}",
            f"**Required Evidence:** {readiness.required_ready}/{readiness.required_total}",
            "",
            "| Layer | Status | Scope | Detail |",
            "| --- | --- | --- | --- |",
            *rows,
        ]
    )


def _render_fundamentals(fundamentals: list[FundamentalSnapshot]) -> str:
    if not fundamentals:
        return "## Fundamentals\n\nNo normalized fundamentals available."

    latest = sorted(
        fundamentals,
        key=lambda item: (item.provenance.as_of_date, item.period_end),
    )[-1]
    rows = []
    for key, value in sorted(latest.metrics.items()):
        rows.append(f"| {key} | {_format_value(value)} |")
    return "\n".join(
        [
            "## Fundamentals",
            "",
            f"**Snapshot As Of:** {latest.provenance.as_of_date.isoformat()}",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
            *rows,
        ]
    )


def _render_valuation_context(fundamentals: list[FundamentalSnapshot]) -> str:
    context = build_valuation_context(fundamentals)
    rows = [
        "| "
        + " | ".join(
            [
                item.label,
                _format_value(item.latest),
                _format_value(item.percentile),
                _format_value(item.low),
                _format_value(item.median),
                _format_value(item.high),
                str(item.observations),
            ]
        )
        + " |"
        for item in context.metrics
        if item.available
    ]
    if not rows:
        return (
            "## Valuation Context\n\n"
            "Fewer than 20 valid cached daily valuation observations are available."
        )
    return "\n".join(
        [
            "## Valuation Context",
            "",
            f"**Daily Snapshot As Of:** {context.as_of_date}",
            f"**Historical Window:** {context.daily_snapshot_count} cached trading days",
            "",
            "| Metric | Latest | Percentile (%) | Low | Median | High | Observations |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            *rows,
        ]
    )


def _render_financial_quality(fundamentals: list[FundamentalSnapshot]) -> str:
    snapshots = [
        item
        for item in fundamentals
        if item.fiscal_period is not None and item.fiscal_period.startswith("financial_report_")
    ]
    if not snapshots:
        return "## Financial Quality\n\nNo disclosed financial quality snapshot available."

    latest = sorted(
        snapshots,
        key=lambda item: (item.provenance.as_of_date, item.period_end),
    )[-1]
    rows = [f"| {key} | {_format_value(value)} |" for key, value in sorted(latest.metrics.items())]
    return "\n".join(
        [
            "## Financial Quality",
            "",
            f"**Report Period:** {latest.period_end.isoformat()}",
            f"**Available As Of:** {latest.provenance.as_of_date.isoformat()}",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
            *rows,
        ]
    )


def _render_financial_health(fundamentals: list[FundamentalSnapshot]) -> str:
    snapshots = [
        item
        for item in fundamentals
        if item.fiscal_period is not None and item.fiscal_period.startswith("financial_report_")
    ]
    if not snapshots:
        return "## Financial Health\n\nNo disclosed financial quality snapshot available."

    latest = sorted(
        snapshots,
        key=lambda item: (item.provenance.as_of_date, item.period_end),
    )[-1]
    assessment = assess_financial_health(latest)
    rows = [
        "| "
        + " | ".join(
            [
                check.name,
                check.status.value,
                _format_value(check.observed),
                _format_value(check.threshold),
            ]
        )
        + " |"
        for check in assessment.checks
    ]
    return "\n".join(
        [
            "## Financial Health",
            "",
            f"**Status:** {assessment.status.value}",
            f"**Healthy Checks:** {assessment.score}/4",
            "",
            "| Check | Status | Observed | Reference Threshold |",
            "| --- | --- | ---: | ---: |",
            *rows,
        ]
    )


def _render_financial_trend(fundamentals: list[FundamentalSnapshot]) -> str:
    snapshots = [
        item
        for item in fundamentals
        if item.fiscal_period is not None and item.fiscal_period.startswith("financial_report_")
    ]
    by_period = {item.period_end: item for item in snapshots}
    history = [item for _, item in sorted(by_period.items(), reverse=True)[:8]]
    if len(history) < 2:
        return (
            "## Financial Trend\n\nFewer than two disclosed financial report periods are available."
        )

    rows = []
    for item in history:
        metrics = item.metrics
        rows.append(
            "| "
            + " | ".join(
                [
                    item.period_end.isoformat(),
                    _format_value(metrics.get("reported_total_revenue")),
                    _format_value(metrics.get("reported_net_income")),
                    _format_value(metrics.get("reported_operating_cashflow")),
                    _format_value(metrics.get("return_on_equity_pct")),
                ]
            )
            + " |"
        )
    return "\n".join(
        [
            "## Financial Trend",
            "",
            "| Report Period | Revenue | Net Income | Operating Cash Flow | ROE (%) |",
            "| --- | ---: | ---: | ---: | ---: |",
            *rows,
        ]
    )


def _render_news(news: list[NewsItem]) -> str:
    if not news:
        return "## News\n\nNo normalized news items available."

    rows = []
    for item in sorted(news, key=lambda item: item.published_at, reverse=True)[:10]:
        title = f"[{item.title}]({item.url})" if item.url else item.title
        rows.append(
            "| "
            + " | ".join(
                [
                    item.published_at.date().isoformat(),
                    item.provider,
                    title,
                ]
            )
            + " |"
        )
    return "\n".join(["## News", "", "| Date | Provider | Title |", "| --- | --- | --- |", *rows])


def _render_agent_outputs(outputs: list[AgentOutputEnvelope]) -> str:
    if not outputs:
        return "## Agent Outputs\n\nNo structured agent outputs available."

    manager = [item for item in outputs if item.metadata.get("stage") == "manager"]
    failed = [item for item in outputs if item.metadata.get("failed") is True]
    debate = [
        item
        for item in outputs
        if item.metadata.get("stage") in {"bull", "bear"} and item not in failed
    ]
    specialists = [
        item
        for item in outputs
        if item.metadata.get("provider")
        and item not in manager
        and item not in debate
        and item not in failed
    ]
    baseline = [
        item for item in outputs if not item.metadata.get("provider") and item not in failed
    ]

    parts = [
        "## Agent Outputs",
        "",
        "> 阅读顺序：先看研究经理综合，再核对多空辩论和专家意见；降级阶段不应作为有效结论。",
    ]
    for title, items in (
        ("研究经理综合", manager),
        ("多空辩论", debate),
        ("专家分析", specialists),
        ("降级或失败阶段", failed),
        ("确定性研究基线", baseline),
    ):
        if not items:
            continue
        parts.extend(["", f"### {title}", ""])
        ordered = sorted(items, key=lambda item: (item.agent_role, item.agent_id))
        parts.append("\n\n".join(_render_readable_agent_output(item) for item in ordered))
    return "\n".join(parts)


def _render_readable_agent_output(output: AgentOutputEnvelope) -> str:
    """Backfill scenario sections when rendering older manager archives."""
    if (
        output.metadata.get("stage") == "manager"
        and isinstance(output.payload, InvestmentThesis)
        and not output.sections
    ):
        thesis = output.payload
        output = output.model_copy(
            update={
                "sections": [
                    AgentOutputSection(
                        title="基础情景", summary=thesis.base_case, evidence=thesis.evidence
                    ),
                    AgentOutputSection(title="乐观情景", summary=thesis.bull_case),
                    AgentOutputSection(title="悲观情景", summary=thesis.bear_case),
                    AgentOutputSection(title="潜在催化剂", bullets=thesis.catalysts),
                    AgentOutputSection(
                        title="反证与失效条件", bullets=thesis.disconfirming_evidence
                    ),
                ]
            }
        )
    return render_agent_output(output)


def _render_analyst_notes(notes: list[AnalystNote]) -> str:
    if not notes:
        return "## Analyst Notes\n\nNo structured analyst notes available."
    rendered = [render_analyst_note(note) for note in notes]
    return "## Analyst Notes\n\n" + "\n\n".join(rendered)


def _render_thesis(thesis: InvestmentThesis | None) -> str:
    if thesis is None:
        return "## Investment Thesis\n\nNo structured thesis available."
    return "## Investment Thesis\n\n" + render_investment_thesis(thesis)


def _render_signal(signal: TradeSignal | None) -> str:
    if signal is None:
        return "## Trade Signal\n\nNo validated trade signal available."
    return "## Trade Signal\n\n" + render_trade_signal(signal)


def _render_risk_review(review: RiskReview | None) -> str:
    if review is None:
        return "## Risk Review\n\nNo deterministic risk review available."

    parts = [
        "## Risk Review",
        "",
        f"**Decision:** {review.decision.value}",
        f"**Approved Position:** {_pct(review.approved_position_pct)}",
    ]
    if review.breaches:
        parts.extend(
            [
                "",
                "| Rule | Severity | Observed | Limit | Action | Message |",
                "| --- | --- | ---: | ---: | --- | --- |",
            ]
        )
        for breach in review.breaches:
            parts.append(
                "| "
                + " | ".join(
                    [
                        breach.rule,
                        breach.severity.value,
                        _format_value(breach.observed),
                        _format_value(breach.limit),
                        breach.recommended_action or "N/A",
                        breach.message,
                    ]
                )
                + " |"
            )
    if review.rule_results:
        parts.extend(["", f"**Rules Evaluated:** {len(review.rule_results)}"])
    if review.notes:
        parts.extend(["", "### Notes", *[f"- {note}" for note in review.notes]])
    return "\n".join(parts)


def _render_backtest(result: BacktestResult | None) -> str:
    if result is None:
        return "## Backtest\n\nNo backtest result available."

    metrics = result.metrics
    parts = [
        "## Backtest",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Total Return | {_pct(metrics.total_return_pct)} |",
        f"| CAGR | {_optional_pct(metrics.cagr_pct)} |",
        f"| Annualized Volatility | {_optional_pct(metrics.annualized_volatility_pct)} |",
        f"| Sharpe | {_optional_number(metrics.sharpe)} |",
        f"| Sortino | {_optional_number(metrics.sortino)} |",
        f"| Max Drawdown | {_pct(metrics.max_drawdown_pct)} |",
        f"| Win Rate | {_optional_pct(metrics.win_rate_pct)} |",
        f"| Profit Factor | {_optional_number(metrics.profit_factor)} |",
        f"| Avg Trade Return | {_optional_pct(metrics.average_trade_return_pct)} |",
        f"| Avg Holding Days | {_optional_number(metrics.average_holding_days)} |",
        f"| Max Consecutive Losses | {_optional_int(metrics.max_consecutive_losses)} |",
        f"| Turnover | {_optional_pct(metrics.turnover_pct)} |",
        f"| Average Exposure | {_optional_pct(metrics.average_exposure_pct)} |",
        "",
        f"**Trades:** {len(result.trades)}",
        f"**Closed Round Trips:** {len(result.round_trips)}",
    ]
    if result.warning_events:
        parts.extend(["", "### Warnings", "| Severity | Code | Message |", "| --- | --- | --- |"])
        for warning in result.warning_events:
            parts.append(f"| {warning.severity.value} | {warning.code} | {warning.message} |")
    elif result.warnings:
        parts.extend(["", "### Warnings", *[f"- {warning}" for warning in result.warnings]])
    return "\n".join(parts)


def _render_provenance(bundle: ResearchReportBundle) -> str:
    rows = []
    for bar in bundle.price_bars:
        rows.append(
            _provenance_row("price", bar.symbol, bar.provenance.provider, bar.provenance.as_of_date)
        )
    for snapshot in bundle.fundamentals:
        rows.append(
            _provenance_row(
                "fundamentals",
                snapshot.symbol,
                snapshot.provenance.provider,
                snapshot.provenance.as_of_date,
            )
        )
    for item in bundle.news:
        rows.append(
            _provenance_row("news", item.symbol or bundle.symbol, item.provider, item.as_of_date)
        )

    if not rows:
        return "## Provenance\n\nNo data provenance available."

    unique_rows = sorted(set(rows))
    return "\n".join(
        [
            "## Provenance",
            "",
            "| Artifact | Symbol | Provider | As Of |",
            "| --- | --- | --- | --- |",
            *unique_rows,
        ]
    )


def _provenance_row(kind: str, symbol: str, provider: str, as_of_date) -> str:
    return f"| {kind} | {symbol} | {provider} | {as_of_date.isoformat()} |"


def _money(value: float, currency: str | None) -> str:
    prefix = f"{currency} " if currency else ""
    return f"{prefix}{value:,.2f}"


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _optional_pct(value: float | None) -> str:
    return "N/A" if value is None else _pct(value)


def _optional_number(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2f}"


def _optional_int(value: int | None) -> str:
    return "N/A" if value is None else str(value)


def _format_value(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:,.4g}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)
