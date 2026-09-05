"""End-to-end personal ticker research workflow."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from .agent_artifacts import (
    agent_output_from_analyst_note,
    agent_output_from_investment_thesis,
    agent_output_from_trade_signal,
)
from .agent_contracts import (
    AgentOutputEnvelope,
    AgentOutputType,
    AnalystNote,
    ConfidenceLevel,
    EvidenceRef,
    InvestmentThesis,
    TradeSignal,
)
from .artifact_store import ArtifactStore, JsonArtifactStore
from .backtest_contracts import BacktestConfig, BacktestResult, ExecutionConfig
from .backtest_engine import run_daily_signal_backtest
from .data_contracts import (
    DataProvider,
    FundamentalSnapshot,
    InstrumentIdentity,
    NewsItem,
    PriceBar,
)
from .game_approvals import JsonGameApprovalStore
from .game_opportunity import build_game_opportunity_snapshot
from .game_universe import build_game_research_snapshot
from .narrative_provider import (
    ResearchNarrativeContext,
    ResearchNarrativeProvider,
    build_game_narrative_evidence,
    build_narrative_evidence,
    validate_narrative_outputs,
)
from .research_report import (
    ResearchReportBundle,
    ResearchRunAudit,
    render_research_report,
    write_research_report,
)
from .risk_contracts import RiskPolicy, RiskReview, evaluate_basic_risk
from .run_archive import ResearchRunArchive, ResearchRunSummary

TECHNICAL_FEATURE_VERSION = "technical-snapshot-v2-adjusted"


class ResearchWorkflowConfig(BaseModel):
    """Configuration for one local ticker research run."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    as_of_date: date
    lookback_days: int = Field(default=90, ge=1)
    currency: str | None = None
    narrative_mode: str = Field(default="deterministic", min_length=1)
    initial_cash: float = Field(default=100_000.0, gt=0)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    current_position_pct: float = Field(default=0.0, ge=0.0, le=1.0)
    portfolio_drawdown_pct: float = Field(default=0.0, ge=0.0, le=1.0)
    realized_volatility_pct: float | None = Field(default=None, gt=0.0)


class ResearchWorkflowResult(BaseModel):
    """Outputs from one workflow run."""

    model_config = ConfigDict(frozen=True)

    bundle: ResearchReportBundle
    markdown: str
    report_path: Path | None = None
    archived_run: ResearchRunSummary | None = None


def run_ticker_research(
    *,
    config: ResearchWorkflowConfig,
    provider: DataProvider,
    store: ArtifactStore | None = None,
    signal: TradeSignal | None = None,
    risk_policy: RiskPolicy | None = None,
    output_dir: str | Path | None = None,
    archive: ResearchRunArchive | None = None,
    narrative_provider: ResearchNarrativeProvider | None = None,
) -> ResearchWorkflowResult:
    """Fetch data, build artifacts, optionally review/backtest, and render a report."""

    identity = InstrumentIdentity(symbol=config.symbol, currency=config.currency)
    start_date = config.as_of_date - timedelta(days=config.lookback_days)

    price_bars = list(
        provider.get_price_bars(
            identity,
            start_date,
            config.as_of_date,
            as_of_date=config.as_of_date,
        )
    )
    fundamentals = list(provider.get_fundamentals(identity, as_of_date=config.as_of_date))
    news = list(
        provider.get_news(
            identity,
            start_date,
            config.as_of_date,
            as_of_date=config.as_of_date,
        )
    )

    if store is not None:
        store.save_price_bars(price_bars)
        store.save_fundamentals(fundamentals)
        store.save_news(news)

    analyst_notes = build_deterministic_notes(
        symbol=config.symbol,
        as_of_date=config.as_of_date,
        price_bars=price_bars,
        fundamentals=fundamentals,
        news=news,
    )
    thesis = build_deterministic_thesis(
        symbol=config.symbol,
        as_of_date=config.as_of_date,
        notes=analyst_notes,
    )
    agent_outputs = build_agent_outputs(
        analyst_notes=analyst_notes,
        thesis=thesis,
        signal=signal,
    )
    if narrative_provider is not None:
        game_research = build_game_research_snapshot(config.symbol, as_of_date=config.as_of_date)
        game_approvals = None
        game_opportunity = None
        if isinstance(store, JsonArtifactStore):
            game_approvals = JsonGameApprovalStore(store.root).digest(
                config.symbol, as_of_date=config.as_of_date
            )
            game_opportunity = build_game_opportunity_snapshot(
                store, config.symbol, as_of_date=config.as_of_date
            )
        deterministic_outputs = [
            output for output in agent_outputs if output.output_type != AgentOutputType.TRADE_SIGNAL
        ]
        deterministic_report_markdown = render_research_report(
            ResearchReportBundle(
                symbol=config.symbol,
                as_of_date=datetime.combine(config.as_of_date, time.min, tzinfo=timezone.utc),
                price_bars=price_bars,
                fundamentals=fundamentals,
                news=news,
                agent_outputs=deterministic_outputs,
                analyst_notes=analyst_notes,
                thesis=thesis,
            )
        )
        context = ResearchNarrativeContext(
            symbol=config.symbol,
            as_of_date=config.as_of_date,
            price_bars=price_bars,
            fundamentals=fundamentals,
            news=news,
            deterministic_outputs=deterministic_outputs,
            deterministic_report_markdown=deterministic_report_markdown,
            game_research=game_research,
            game_approvals=game_approvals,
            game_opportunity=game_opportunity,
            evidence=[
                *build_narrative_evidence(
                    symbol=config.symbol,
                    as_of_date=config.as_of_date,
                    price_bars=price_bars,
                    fundamentals=fundamentals,
                    news=news,
                ),
                *build_game_narrative_evidence(
                    game_research=game_research,
                    game_approvals=game_approvals,
                ),
            ],
        )
        agent_outputs.extend(
            validate_narrative_outputs(context, narrative_provider.generate(context))
        )
    if store is not None:
        store.save_agent_outputs(agent_outputs)

    risk_review: RiskReview | None = None
    backtest_result: BacktestResult | None = None
    if signal is not None:
        policy = risk_policy or RiskPolicy()
        risk_review = evaluate_basic_risk(
            signal,
            policy,
            current_position_pct=config.current_position_pct,
            portfolio_drawdown_pct=config.portfolio_drawdown_pct,
            realized_volatility_pct=config.realized_volatility_pct,
        )
        backtest_signal = signal.model_copy(
            update={"proposed_position_pct": risk_review.approved_position_pct}
        )
        backtest_result = run_daily_signal_backtest(
            config=BacktestConfig(
                start_date=start_date,
                end_date=config.as_of_date,
                initial_cash=config.initial_cash,
                symbols=[config.symbol],
                execution=config.execution,
            ),
            price_bars=price_bars,
            signals=[backtest_signal],
        )

    run_audit = build_run_audit(
        config=config,
        provider=provider,
        narrative_provider=narrative_provider,
        price_bars=price_bars,
        fundamentals=fundamentals,
        news=news,
        agent_outputs=agent_outputs,
    )
    bundle = ResearchReportBundle(
        symbol=config.symbol,
        as_of_date=datetime.combine(config.as_of_date, time.min, tzinfo=timezone.utc),
        price_bars=price_bars,
        run_audit=run_audit,
        fundamentals=fundamentals,
        news=news,
        agent_outputs=agent_outputs,
        analyst_notes=analyst_notes,
        thesis=thesis,
        signal=signal,
        risk_review=risk_review,
        backtest_result=backtest_result,
    )
    markdown = render_research_report(bundle)
    report_path = write_research_report(bundle, output_dir) if output_dir is not None else None
    archived_run = archive.save_bundle(bundle) if archive is not None else None
    return ResearchWorkflowResult(
        bundle=bundle,
        markdown=markdown,
        report_path=report_path,
        archived_run=archived_run,
    )


def build_run_audit(
    *,
    config: ResearchWorkflowConfig,
    provider: DataProvider,
    narrative_provider: ResearchNarrativeProvider | None,
    price_bars: Sequence[PriceBar],
    fundamentals: Sequence[FundamentalSnapshot],
    news: Sequence[NewsItem],
    agent_outputs: Sequence[AgentOutputEnvelope],
) -> ResearchRunAudit:
    model_outputs = [
        output for output in agent_outputs if isinstance(output.metadata.get("provider"), str)
    ]
    metadata = model_outputs[0].metadata if model_outputs else {}
    llm_provider = metadata.get("provider")
    llm_model = metadata.get("model")
    prompt_versions = sorted(
        {
            str(version)
            for output in model_outputs
            if (version := output.metadata.get("prompt_version"))
        }
    )
    adjusted_count = sum(bar.adjusted_close is not None for bar in price_bars)
    price_basis = (
        "forward_adjusted"
        if price_bars and adjusted_count == len(price_bars)
        else "mixed"
        if adjusted_count
        else "raw_unadjusted"
    )
    usage: dict[str, int | float] = {}
    for output in model_outputs:
        for key, value in output.metadata.items():
            if (
                key.startswith("usage_")
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
            ):
                usage[key.removeprefix("usage_")] = usage.get(key.removeprefix("usage_"), 0) + value

    return ResearchRunAudit(
        narrative_mode=config.narrative_mode,
        data_provider=getattr(provider, "name", provider.__class__.__name__),
        llm_provider=str(llm_provider) if llm_provider else None,
        llm_model=str(llm_model) if llm_model else None,
        llm_endpoint=_llm_endpoint_identifier(narrative_provider, llm_provider),
        prompt_versions=prompt_versions,
        technical_feature_version=TECHNICAL_FEATURE_VERSION,
        context_fingerprint=_context_fingerprint(
            config=config,
            price_bars=price_bars,
            fundamentals=fundamentals,
            news=news,
        ),
        price_basis=price_basis,
        price_bar_count=len(price_bars),
        adjusted_price_bar_count=adjusted_count,
        successful_model_stages=sum(
            not bool(output.metadata.get("failed")) for output in model_outputs
        ),
        degraded_model_stages=sum(bool(output.metadata.get("failed")) for output in model_outputs),
        total_model_latency_ms=sum(
            int(output.metadata.get("latency_ms") or 0) for output in model_outputs
        ),
        usage=usage,
    )


def _llm_endpoint_identifier(
    narrative_provider: ResearchNarrativeProvider | None,
    provider_name: Any,
) -> str | None:
    if not provider_name:
        return None
    provider_config = getattr(narrative_provider, "config", None)
    base_url = getattr(provider_config, "base_url", None)
    if not base_url:
        return f"{provider_name}:provider-default"
    parsed = urlparse(str(base_url))
    if not parsed.hostname:
        return f"{provider_name}:custom-endpoint"
    host = parsed.hostname
    if parsed.port:
        host = f"{host}:{parsed.port}"
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme or 'https'}://{host}{path}"


def _context_fingerprint(
    *,
    config: ResearchWorkflowConfig,
    price_bars: Sequence[PriceBar],
    fundamentals: Sequence[FundamentalSnapshot],
    news: Sequence[NewsItem],
) -> str:
    payload = {
        "symbol": config.symbol,
        "as_of_date": config.as_of_date.isoformat(),
        "lookback_days": config.lookback_days,
        "prices": [
            {
                "date": bar.date.isoformat(),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "adjusted_close": bar.adjusted_close,
                "volume": bar.volume,
                "source": bar.provenance.source,
            }
            for bar in sorted(price_bars, key=lambda item: item.date)
        ],
        "fundamentals": [
            {
                "period_end": item.period_end.isoformat(),
                "fiscal_period": item.fiscal_period,
                "metrics": item.metrics,
                "as_of_date": item.provenance.as_of_date.isoformat(),
                "source": item.provenance.source,
            }
            for item in fundamentals
        ],
        "news": [
            {
                "source_id": item.source_id,
                "published_at": item.published_at.isoformat(),
                "title": item.title,
            }
            for item in news
        ],
    }
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return f"sha256:{sha256(serialized.encode('utf-8')).hexdigest()}"


def build_agent_outputs(
    *,
    analyst_notes: Sequence[AnalystNote],
    thesis: InvestmentThesis | None,
    signal: TradeSignal | None = None,
) -> list[AgentOutputEnvelope]:
    """Create standard envelopes for all agent-like workflow artifacts."""

    outputs = [agent_output_from_analyst_note(note) for note in analyst_notes]
    if thesis is not None:
        outputs.append(agent_output_from_investment_thesis(thesis))
    if signal is not None:
        outputs.append(agent_output_from_trade_signal(signal))
    return outputs


def build_deterministic_notes(
    *,
    symbol: str,
    as_of_date: date,
    price_bars: Sequence[PriceBar],
    fundamentals: Sequence[FundamentalSnapshot],
    news: Sequence[NewsItem],
) -> list[AnalystNote]:
    """Create lightweight deterministic notes from normalized records."""

    notes: list[AnalystNote] = []
    if price_bars:
        notes.append(_market_note(symbol, as_of_date, list(price_bars)))
    if fundamentals:
        notes.append(_fundamentals_note(symbol, as_of_date, list(fundamentals)))
    if news:
        notes.append(_news_note(symbol, as_of_date, list(news)))
    return notes


def build_deterministic_thesis(
    *,
    symbol: str,
    as_of_date: date,
    notes: Sequence[AnalystNote],
) -> InvestmentThesis | None:
    """Create a neutral thesis package from available deterministic notes."""

    if not notes:
        return None

    summaries = "\n\n".join(f"{note.analyst_role}: {note.summary}" for note in notes)
    evidence = [ref for note in notes for ref in note.evidence]
    return InvestmentThesis(
        symbol=symbol,
        as_of_date=as_of_date,
        base_case=summaries,
        bull_case="Bull case requires agent or analyst interpretation beyond deterministic data collection.",
        bear_case="Bear case requires agent or analyst interpretation beyond deterministic data collection.",
        catalysts=[],
        disconfirming_evidence=[],
        evidence=evidence,
        confidence=0.5,
    )


def _market_note(symbol: str, as_of_date: date, price_bars: list[PriceBar]) -> AnalystNote:
    ordered = sorted(price_bars, key=lambda bar: bar.date)
    first = ordered[0]
    last = ordered[-1]
    change = last.close / first.close - 1.0 if first.close else 0.0
    evidence = [
        EvidenceRef(
            source_id=f"price:{symbol}:{first.date.isoformat()}:{last.date.isoformat()}",
            description=f"{len(ordered)} daily bars from {first.date} to {last.date}",
            as_of_date=last.provenance.as_of_date,
            confidence=0.9,
        )
    ]
    return AnalystNote(
        symbol=symbol,
        analyst_role="Market Snapshot",
        as_of_date=as_of_date,
        summary=(
            f"Price moved {_pct(change)} from {first.close:.2f} to {last.close:.2f} "
            f"across {len(ordered)} normalized daily bars."
        ),
        evidence=evidence,
        confidence=ConfidenceLevel.MEDIUM,
    )


def _fundamentals_note(
    symbol: str,
    as_of_date: date,
    fundamentals: list[FundamentalSnapshot],
) -> AnalystNote:
    latest = sorted(
        fundamentals,
        key=lambda item: (item.provenance.as_of_date, item.period_end),
    )[-1]
    metric_names = sorted(latest.metrics)[:6]
    evidence = [
        EvidenceRef(
            source_id=f"fundamentals:{symbol}:{latest.provenance.as_of_date.isoformat()}",
            description=f"{len(latest.metrics)} normalized fundamental metrics",
            as_of_date=latest.provenance.as_of_date,
            confidence=0.85,
        )
    ]
    return AnalystNote(
        symbol=symbol,
        analyst_role="Fundamentals Snapshot",
        as_of_date=as_of_date,
        summary="Latest snapshot includes: " + ", ".join(metric_names) + ".",
        evidence=evidence,
        confidence=ConfidenceLevel.MEDIUM,
    )


def _news_note(symbol: str, as_of_date: date, news: list[NewsItem]) -> AnalystNote:
    ordered = sorted(news, key=lambda item: item.published_at, reverse=True)
    latest_titles = [item.title for item in ordered[:3]]
    evidence = [
        EvidenceRef(
            source_id=f"news:{symbol}:{as_of_date.isoformat()}",
            description=f"{len(news)} normalized news items",
            as_of_date=as_of_date,
            confidence=0.75,
        )
    ]
    return AnalystNote(
        symbol=symbol,
        analyst_role="News Snapshot",
        as_of_date=as_of_date,
        summary="Recent headlines: " + "; ".join(latest_titles) + ".",
        evidence=evidence,
        confidence=ConfidenceLevel.MEDIUM,
    )


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"
