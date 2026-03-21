"""Bridge between macro scanner output and TradingAgents per-ticker analysis."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from tradingagents.agents.utils.json_utils import extract_json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Literal


logger = logging.getLogger(__name__)

ConvictionLevel = Literal["high", "medium", "low"]

CONVICTION_RANK: dict[str, int] = {"high": 3, "medium": 2, "low": 1}


@dataclass
class MacroContext:
    """Macro-level context from scanner output."""

    economic_cycle: str
    central_bank_stance: str
    geopolitical_risks: list[str]
    key_themes: list[dict]  # [{theme, description, conviction, timeframe}]
    executive_summary: str
    risk_factors: list[str]
    timeframe: str = "1 month"
    region: str = "Global"


@dataclass
class StockCandidate:
    """A stock surfaced by the macro scanner."""

    ticker: str
    name: str
    sector: str
    rationale: str
    thesis_angle: str  # growth | value | catalyst | turnaround | defensive | momentum
    conviction: ConvictionLevel
    key_catalysts: list[str]
    risks: list[str]
    macro_theme: str = ""  # which macro theme this stock is linked to


@dataclass
class TickerResult:
    """TradingAgents output for one ticker, enriched with macro context."""

    ticker: str
    candidate: StockCandidate
    macro_context: MacroContext
    analysis_date: str

    # TradingAgents reports (populated after propagate())
    market_report: str = ""
    sentiment_report: str = ""
    news_report: str = ""
    fundamentals_report: str = ""
    investment_debate: str = ""
    trader_investment_plan: str = ""
    risk_debate: str = ""
    final_trade_decision: str = ""

    error: str | None = None


# ─── Parsing ──────────────────────────────────────────────────────────────────


def parse_macro_output(path: Path) -> tuple[MacroContext, list[StockCandidate]]:
    """Parse the JSON output from the Macro Intelligence Agent.

    Args:
        path: Path to the JSON file produced by the macro scanner.

    Returns:
        Tuple of (MacroContext, list of StockCandidate).
    """
    raw_text = path.read_text()
    data = extract_json(raw_text)

    ctx_raw = data.get("macro_context", {})
    macro_context = MacroContext(
        economic_cycle=ctx_raw.get("economic_cycle", ""),
        central_bank_stance=ctx_raw.get("central_bank_stance", ""),
        geopolitical_risks=ctx_raw.get("geopolitical_risks", []),
        key_themes=data.get("key_themes", []),
        executive_summary=data.get("executive_summary", ""),
        risk_factors=data.get("risk_factors", []),
        timeframe=data.get("timeframe", "1 month"),
        region=data.get("region", "Global"),
    )

    candidates: list[StockCandidate] = []
    for s in data.get("stocks_to_investigate", []):
        theme = _match_theme(s.get("sector", ""), data.get("key_themes", []))
        candidates.append(
            StockCandidate(
                ticker=s["ticker"].upper(),
                name=s.get("name", s["ticker"]),
                sector=s.get("sector", ""),
                rationale=s.get("rationale", ""),
                thesis_angle=s.get("thesis_angle", ""),
                conviction=s.get("conviction", "medium"),
                key_catalysts=s.get("key_catalysts", []),
                risks=s.get("risks", []),
                macro_theme=theme,
            )
        )

    return macro_context, candidates


def _match_theme(sector: str, themes: list[dict]) -> str:
    """Return the macro theme name most likely linked to this sector.

    Args:
        sector: Sector name for a stock candidate.
        themes: List of macro theme dicts from the scanner output.

    Returns:
        The matched theme name, or the first theme name, or empty string.
    """
    sector_lower = sector.lower()
    for t in themes:
        desc = (t.get("description", "") + t.get("theme", "")).lower()
        if sector_lower in desc or any(w in desc for w in sector_lower.split()):
            return t.get("theme", "")
    return themes[0].get("theme", "") if themes else ""


# ─── Core pipeline ────────────────────────────────────────────────────────────


def filter_candidates(
    candidates: list[StockCandidate],
    min_conviction: ConvictionLevel,
    ticker_filter: list[str] | None,
) -> list[StockCandidate]:
    """Filter by conviction level and optional explicit ticker list.

    Args:
        candidates: All stock candidates from the macro scanner.
        min_conviction: Minimum conviction threshold ("high", "medium", or "low").
        ticker_filter: Optional list of tickers to restrict to.

    Returns:
        Filtered and sorted list (high conviction first, then alphabetically).
    """
    min_rank = CONVICTION_RANK[min_conviction]
    filtered = [c for c in candidates if CONVICTION_RANK[c.conviction] >= min_rank]
    if ticker_filter:
        tickers_upper = {t.upper() for t in ticker_filter}
        filtered = [c for c in filtered if c.ticker in tickers_upper]
    filtered.sort(key=lambda c: (-CONVICTION_RANK[c.conviction], c.ticker))
    return filtered


def run_ticker_analysis(
    candidate: StockCandidate,
    macro_context: MacroContext,
    config: dict,
    analysis_date: str,
) -> TickerResult:
    """Run the full TradingAgents pipeline for one ticker.

    NOTE: TradingAgentsGraph is synchronous — call this from a thread pool
    when running multiple tickers concurrently (see run_all_tickers).
    """
    result = TickerResult(
        ticker=candidate.ticker,
        candidate=candidate,
        macro_context=macro_context,
        analysis_date=analysis_date,
    )

    t0 = time.monotonic()
    logger.info(
        "[%s] ▶ Starting analysis (%s, %s conviction)",
        candidate.ticker, candidate.sector, candidate.conviction,
    )

    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.observability import get_run_logger

        rl = get_run_logger()
        cbs = [rl.callback] if rl else None
        ta = TradingAgentsGraph(debug=False, config=config, callbacks=cbs)
        final_state, decision = ta.propagate(candidate.ticker, analysis_date)

        result.market_report = final_state.get("market_report", "")
        result.sentiment_report = final_state.get("sentiment_report", "")
        result.news_report = final_state.get("news_report", "")
        result.fundamentals_report = final_state.get("fundamentals_report", "")
        result.investment_debate = str(final_state.get("investment_debate_state", ""))
        result.trader_investment_plan = final_state.get("trader_investment_plan", "")
        result.risk_debate = str(final_state.get("risk_debate_state", ""))
        result.final_trade_decision = decision

        elapsed = time.monotonic() - t0
        logger.info(
            "[%s] ✓ Analysis complete in %.0fs — decision: %s",
            candidate.ticker, elapsed, str(decision)[:80],
        )

    except Exception as exc:
        elapsed = time.monotonic() - t0
        logger.error(
            "[%s] ✗ Analysis FAILED after %.0fs: %s",
            candidate.ticker, elapsed, exc, exc_info=True,
        )
        result.error = str(exc)

    return result



async def run_all_tickers(
    candidates: list[StockCandidate],
    macro_context: MacroContext,
    config: dict,
    analysis_date: str,
    max_concurrent: int = 2,
    on_ticker_done: Callable[[TickerResult, int, int], None] | None = None,
) -> list[TickerResult]:
    """Run TradingAgents for every candidate with controlled concurrency.

    max_concurrent=2 is conservative — each run makes many API calls.
    Increase only if your data vendor plan supports higher rate limits.

    Args:
        candidates: Filtered stock candidates to analyse.
        macro_context: Macro context shared across all tickers.
        config: TradingAgents configuration dict.
        analysis_date: Date string in YYYY-MM-DD format.
        max_concurrent: Maximum number of tickers to process in parallel.
        on_ticker_done: Optional callback(result, done_count, total_count) fired
            after each ticker finishes — use this to drive a progress bar.

    Returns:
        List of TickerResult in completion order.
    """
    loop = asyncio.get_running_loop()
    total = len(candidates)
    results: list[TickerResult] = []

    # Use a semaphore so at most max_concurrent tickers run simultaneously,
    # but we still get individual completion callbacks via as_completed.
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _run_one(candidate: StockCandidate) -> TickerResult:
        async with semaphore:
            return await loop.run_in_executor(
                None,  # use default ThreadPoolExecutor
                run_ticker_analysis,
                candidate,
                macro_context,
                config,
                analysis_date,
            )

    tasks = [asyncio.create_task(_run_one(c)) for c in candidates]
    done_count = 0
    for coro in asyncio.as_completed(tasks):
        result = await coro
        done_count += 1
        results.append(result)
        if on_ticker_done is not None:
            try:
                on_ticker_done(result, done_count, total)
            except Exception:  # never let a callback crash the pipeline
                pass

    return results



# ─── Reporting ────────────────────────────────────────────────────────────────


def _macro_preamble(ctx: MacroContext) -> str:
    """Render the macro context block shared across all reports."""
    themes_text = "\n".join(
        f"  - **{t['theme']}** ({t.get('conviction', '?')} conviction): {t.get('description', '')}"
        for t in ctx.key_themes[:5]
    )
    risks_text = "\n".join(f"  - {r}" for r in ctx.risk_factors[:5])
    return f"""## Macro context (from Macro Intelligence Agent)

**Horizon:** {ctx.timeframe} | **Region:** {ctx.region}

**Economic cycle:** {ctx.economic_cycle}

**Central bank stance:** {ctx.central_bank_stance}

**Key macro themes:**
{themes_text}

**Geopolitical risks:** {', '.join(ctx.geopolitical_risks)}

**Macro risk factors:**
{risks_text}

**Executive summary:** {ctx.executive_summary}

---
"""


def render_ticker_report(result: TickerResult) -> str:
    """Render a single ticker's full Markdown report.

    Args:
        result: Completed TickerResult (may contain an error).

    Returns:
        Markdown string with the full analysis or failure notice.
    """
    c = result.candidate
    header = f"""# {c.ticker} — {c.name}
**Sector:** {c.sector} | **Thesis:** {c.thesis_angle} | **Conviction:** {c.conviction.upper()}
**Analysis date:** {result.analysis_date}

### Macro rationale (why this stock was surfaced)
{c.rationale}

**Macro theme alignment:** {c.macro_theme}
**Key catalysts:** {', '.join(c.key_catalysts)}
**Macro-level risks:** {', '.join(c.risks)}

---
"""
    if result.error:
        return header + f"## Analysis failed\n```\n{result.error}\n```\n"

    return (
        header
        + _macro_preamble(result.macro_context)
        + f"## Market analysis\n{result.market_report}\n\n"
        + f"## Fundamentals analysis\n{result.fundamentals_report}\n\n"
        + f"## News analysis\n{result.news_report}\n\n"
        + f"## Sentiment analysis\n{result.sentiment_report}\n\n"
        + f"## Research team debate (Bull vs Bear)\n{result.investment_debate}\n\n"
        + f"## Trader investment plan\n{result.trader_investment_plan}\n\n"
        + f"## Risk management assessment\n{result.risk_debate}\n\n"
        + f"## Final trade decision\n{result.final_trade_decision}\n"
    )


def render_combined_summary(
    results: list[TickerResult],
    macro_context: MacroContext,
) -> str:
    """Render a single summary Markdown combining all tickers.

    Args:
        results: All completed TickerResults.
        macro_context: Shared macro context for the preamble.

    Returns:
        Markdown string with overview table and per-ticker decisions.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# Macro-Driven Deep Dive Summary",
        f"Generated: {now}\n",
        _macro_preamble(macro_context),
        "## Results overview\n",
        "| Ticker | Name | Conviction | Sector | Decision |",
        "|--------|------|-----------|--------|---------|",
    ]

    for r in results:
        decision_preview = (
            "ERROR"
            if r.error
            else str(r.final_trade_decision)[:60].replace("\n", " ")
        )
        lines.append(
            f"| {r.ticker} | {r.candidate.name} "
            f"| {r.candidate.conviction.upper()} "
            f"| {r.candidate.sector} "
            f"| {decision_preview} |"
        )

    lines.append("\n---\n")
    for r in results:
        lines.append(f"## {r.ticker} — final decision\n")
        if r.error:
            lines.append(f"Analysis failed: {r.error}\n")
        else:
            lines.append(f"**Macro rationale:** {r.candidate.rationale}\n\n")
            lines.append(r.final_trade_decision or "_No decision generated._")
            lines.append("\n\n---\n")

    return "\n".join(lines)


def save_results(
    results: list[TickerResult],
    macro_context: MacroContext,
    output_dir: Path,
) -> None:
    """Save per-ticker Markdown reports, a combined summary, and a JSON index.

    Args:
        results: All completed TickerResults.
        macro_context: Shared macro context used in reports.
        output_dir: Directory to write all output files into.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    for result in results:
        ticker_dir = output_dir / result.ticker
        ticker_dir.mkdir(exist_ok=True)
        report_path = ticker_dir / f"{result.analysis_date}_deep_dive.md"
        report_path.write_text(render_ticker_report(result))
        logger.info("Saved report: %s", report_path)

    summary_path = output_dir / "summary.md"
    summary_path.write_text(render_combined_summary(results, macro_context))
    logger.info("Saved summary: %s", summary_path)

    # Machine-readable index for downstream tooling
    json_path = output_dir / "results.json"
    json_path.write_text(
        json.dumps(
            [
                {
                    "ticker": r.ticker,
                    "name": r.candidate.name,
                    "sector": r.candidate.sector,
                    "conviction": r.candidate.conviction,
                    "thesis_angle": r.candidate.thesis_angle,
                    "analysis_date": r.analysis_date,
                    "final_trade_decision": r.final_trade_decision,
                    "error": r.error,
                }
                for r in results
            ],
            indent=2,
        )
    )
    logger.info("Saved JSON index: %s", json_path)


# ─── Facade ───────────────────────────────────────────────────────────────────


class MacroBridge:
    """Facade for the macro scanner → TradingAgents pipeline.

    Provides a single entry point for CLI and programmatic use without
    exposing the individual pipeline functions.
    """

    def __init__(self, config: dict) -> None:
        """
        Args:
            config: TradingAgents configuration dict (built by the caller/CLI).
        """
        self.config = config

    def load(self, path: Path) -> tuple[MacroContext, list[StockCandidate]]:
        """Parse macro scanner JSON output.

        Args:
            path: Path to the macro scanner JSON file.

        Returns:
            Tuple of (MacroContext, all StockCandidates).
        """
        return parse_macro_output(path)

    def filter(
        self,
        candidates: list[StockCandidate],
        min_conviction: ConvictionLevel = "medium",
        ticker_filter: list[str] | None = None,
    ) -> list[StockCandidate]:
        """Filter and sort stock candidates.

        Args:
            candidates: All candidates from load().
            min_conviction: Minimum conviction threshold.
            ticker_filter: Optional explicit ticker whitelist.

        Returns:
            Filtered and sorted candidate list.
        """
        return filter_candidates(candidates, min_conviction, ticker_filter)

    def run(
        self,
        candidates: list[StockCandidate],
        macro_context: MacroContext,
        analysis_date: str,
        max_concurrent: int = 2,
    ) -> list[TickerResult]:
        """Run the full TradingAgents pipeline for all candidates.

        Blocks until all tickers are complete.

        Args:
            candidates: Filtered candidates to analyse.
            macro_context: Macro context for enriching results.
            analysis_date: Date string in YYYY-MM-DD format.
            max_concurrent: Maximum parallel tickers.

        Returns:
            List of TickerResult.
        """
        return asyncio.run(
            run_all_tickers(
                candidates=candidates,
                macro_context=macro_context,
                config=self.config,
                analysis_date=analysis_date,
                max_concurrent=max_concurrent,
            )
        )

    def save(
        self,
        results: list[TickerResult],
        macro_context: MacroContext,
        output_dir: Path,
    ) -> None:
        """Save results to disk.

        Args:
            results: Completed TickerResults.
            macro_context: Shared macro context.
            output_dir: Target directory for all output files.
        """
        save_results(results, macro_context, output_dir)
