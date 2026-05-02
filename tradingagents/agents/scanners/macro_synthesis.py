import json
import logging
import re
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from langchain_core.prompts import ChatPromptTemplate

from tradingagents.agents.utils.json_utils import extract_json, sanitize_llm_output
from tradingagents.agents.utils.llm_guard import invoke_with_timeout
from tradingagents.agents.utils.scanner_idempotency import (
    check_and_load_report,
    require_scan_context,
    save_node_report,
)
from tradingagents.agents.utils.scanner_states import ScannerState
from tradingagents.dataflows.macro_regime import classify_macro_regime, format_macro_report
from tradingagents.default_config import DEFAULT_CONFIG

logger = logging.getLogger(__name__)
_TICKER_RE = re.compile(r"\b[A-Z]{1,5}\b")
_STRICT_TICKER_RE = re.compile(r"^[A-Z]{1,5}$")
_TICKER_STOPWORDS = {
    "A",
    "I",
    "AI",
    "AN",
    "AND",
    "ARE",
    "AS",
    "AT",
    "BE",
    "BY",
    "END",
    "ETF",
    "GDP",
    "GICS",
    "JSON",
    "LOW",
    "NFP",
    "NOT",
    "NOW",
    "OIL",
    "ONLY",
    "OR",
    "THE",
    "TO",
    "USD",
    "VIX",
    "YTD",
    "CPI",
    "PPI",
    "EPS",
    "CEO",
    "CFO",
    "N/A",
    # Exchange codes that appear in the gatekeeper universe report's Exchange column
    "NMS",
    "NYQ",
    "ASE",
}
_CANONICAL_REGIME_LABELS = {
    "risk-on": "RISK-ON",
    "risk-off": "RISK-OFF",
    "transition": "TRANSITION",
}
_CANONICAL_CONFIDENCE_VALUES = {"high", "medium", "low"}


def _format_horizon_label(scan_horizon_days: int) -> str:
    if scan_horizon_days not in (30, 60, 90):
        logger.warning(
            "macro_synthesis: unsupported scan_horizon_days=%s; defaulting to 30",
            scan_horizon_days,
        )
        scan_horizon_days = 30

    if scan_horizon_days == 30:
        return "1 month"
    if scan_horizon_days == 60:
        return "2 months"
    return "3 months"


def _extract_rankable_tickers(text: str) -> set[str]:
    if not text:
        return set()
    return {
        token
        for token in _TICKER_RE.findall(text)
        if token not in _TICKER_STOPWORDS and len(token) > 1
    }


def _parse_gatekeeper_rows(report_text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not report_text:
        return rows

    for line in report_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 2:
            continue
        ticker = cells[0].upper()
        if ticker == "SYMBOL" or set(ticker) == {"-"}:
            continue
        if not _STRICT_TICKER_RE.fullmatch(ticker):
            continue
        if ticker in _TICKER_STOPWORDS:
            continue
        rows.append({"ticker": ticker, "name": cells[1]})
    return rows


def _build_candidate_rankings(state: ScannerState, limit: int = 15) -> list[dict[str, object]]:
    allowed_tickers = _extract_rankable_tickers(state.get("gatekeeper_universe_report", ""))
    weighted_sources = [
        ("market_movers_report", 2, "market_movers"),
        ("smart_money_report", 2, "smart_money"),
        ("factor_alignment_report", 3, "factor_alignment"),
        ("drift_opportunities_report", 3, "drift"),
        ("industry_deep_dive_report", 1, "industry_deep_dive"),
    ]

    scores: dict[str, int] = defaultdict(int)
    sources: dict[str, list[str]] = defaultdict(list)

    for state_key, weight, label in weighted_sources:
        tickers = _extract_rankable_tickers(state.get(state_key, ""))
        for ticker in tickers:
            if allowed_tickers and ticker not in allowed_tickers:
                continue
            scores[ticker] += weight
            sources[ticker].append(label)

    ranked = sorted(
        (
            {
                "ticker": ticker,
                "score": score,
                "sources": sorted(sources[ticker]),
                "source_count": len(sources[ticker]),
            }
            for ticker, score in scores.items()
        ),
        key=lambda row: (row["score"], row["source_count"], row["ticker"]),
        reverse=True,
    )
    return ranked[:limit]


def _normalize_candidate_item(
    item: object,
    gatekeeper_lookup: dict[str, dict[str, str]],
) -> dict[str, object] | None:
    if isinstance(item, dict):
        candidate = dict(item)
        ticker = str(candidate.get("ticker") or candidate.get("symbol") or "").strip().upper()
    elif isinstance(item, str):
        ticker = item.strip().upper()
        candidate = {"ticker": ticker}
    else:
        return None

    if not ticker or not _STRICT_TICKER_RE.fullmatch(ticker):
        return None
    if ticker in _TICKER_STOPWORDS:
        return None
    if gatekeeper_lookup and ticker not in gatekeeper_lookup:
        return None

    gatekeeper_row = gatekeeper_lookup.get(ticker, {})
    candidate["ticker"] = ticker
    candidate["name"] = str(candidate.get("name") or gatekeeper_row.get("name") or ticker)
    candidate["sector"] = str(candidate.get("sector") or "Unknown")
    candidate["rationale"] = str(
        candidate.get("rationale") or "Candidate selected from scanner synthesis output."
    )
    candidate["thesis_angle"] = str(candidate.get("thesis_angle") or "momentum")
    candidate["conviction"] = str(candidate.get("conviction") or "medium")
    candidate["key_catalysts"] = list(candidate.get("key_catalysts") or [])
    candidate["risks"] = list(candidate.get("risks") or [])
    return candidate


def _fallback_candidate_from_ranking(
    ticker: str,
    gatekeeper_lookup: dict[str, dict[str, str]],
    ranking_row: dict[str, object] | None = None,
) -> dict[str, object]:
    sources = list((ranking_row or {}).get("sources") or [])
    source_label = ", ".join(sources) if sources else "gatekeeper universe"
    catalysts = []
    if ranking_row:
        catalysts.append(
            f"Appeared across {int(ranking_row.get('source_count') or 0)} scanner streams."
        )
        catalysts.append(
            f"Deterministic overlap score={int(ranking_row.get('score') or 0)} from {source_label}."
        )
    else:
        catalysts.append("Passed gatekeeper liquidity and quality filters.")
        catalysts.append("Backfilled because the LLM returned fewer candidates than configured.")

    return {
        "ticker": ticker,
        "name": gatekeeper_lookup.get(ticker, {}).get("name", ticker),
        "sector": "Unknown",
        "rationale": (
            "Deterministic fallback candidate selected from "
            f"{source_label}. Review the upstream scanner reports before trading."
        ),
        "thesis_angle": "momentum",
        "conviction": "medium",
        "key_catalysts": catalysts,
        "risks": [
            "Candidate was backfilled deterministically after an underfilled LLM summary.",
            "Sector-specific thesis details should be validated against the source reports.",
        ],
    }


def _canonical_regime_from_data(regime_data: dict) -> dict[str, object]:
    regime = str(regime_data.get("regime") or "").strip().lower()
    label = _CANONICAL_REGIME_LABELS.get(regime)
    if label is None:
        raise RuntimeError(
            "Macro regime classifier did not produce a canonical regime label "
            f"(got {regime_data.get('regime')!r})."
        )

    score = regime_data.get("score")
    if isinstance(score, bool) or not isinstance(score, int):
        raise RuntimeError(
            "Macro regime classifier did not produce an integer score "
            f"(got {score!r})."
        )

    confidence = str(regime_data.get("confidence") or "").strip().lower()
    if confidence not in _CANONICAL_CONFIDENCE_VALUES:
        raise RuntimeError(
            "Macro regime classifier did not produce a canonical confidence "
            f"(got {regime_data.get('confidence')!r})."
        )

    return {"label": label, "score": score, "confidence": confidence}


def _validate_macro_regime_report(report: str, canonical_regime: dict[str, object]) -> None:
    if not report:
        raise RuntimeError("Macro regime formatter did not produce a report.")

    label = str(canonical_regime["label"])
    if label not in report:
        raise RuntimeError(
            "Macro regime formatter did not include the canonical label "
            f"{label!r} in the report."
        )

    signed_score = f"{int(canonical_regime['score']):+d}"
    if signed_score not in report:
        raise RuntimeError(
            "Macro regime formatter did not include the canonical score "
            f"{signed_score!r} in the report."
        )


def _repair_macro_summary(
    parsed: dict,
    state: ScannerState,
    max_scan_tickers: int,
    horizon_label: str,
) -> dict:
    repaired = dict(parsed or {})
    repaired["timeframe"] = str(repaired.get("timeframe") or horizon_label)

    gatekeeper_rows = _parse_gatekeeper_rows(state.get("gatekeeper_universe_report", ""))
    gatekeeper_lookup = {row["ticker"]: row for row in gatekeeper_rows}
    ranking_rows = _build_candidate_rankings(state, limit=max(max_scan_tickers * 3, 15))
    ranking_lookup = {str(row["ticker"]): row for row in ranking_rows}

    raw_candidates = repaired.get("stocks_to_investigate")
    if not isinstance(raw_candidates, list):
        raw_candidates = []

    normalized_candidates: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in raw_candidates:
        candidate = _normalize_candidate_item(item, gatekeeper_lookup)
        if not candidate:
            continue
        ticker = str(candidate["ticker"])
        if ticker in seen:
            continue
        seen.add(ticker)
        normalized_candidates.append(candidate)

    if len(normalized_candidates) < max_scan_tickers:
        for row in ranking_rows:
            ticker = str(row["ticker"])
            if ticker in seen or (gatekeeper_lookup and ticker not in gatekeeper_lookup):
                continue
            normalized_candidates.append(
                _fallback_candidate_from_ranking(
                    ticker, gatekeeper_lookup, ranking_lookup.get(ticker)
                )
            )
            seen.add(ticker)
            if len(normalized_candidates) >= max_scan_tickers:
                break

    if len(normalized_candidates) < max_scan_tickers:
        for row in gatekeeper_rows:
            ticker = row["ticker"]
            if ticker in seen:
                continue
            normalized_candidates.append(
                _fallback_candidate_from_ranking(ticker, gatekeeper_lookup)
            )
            seen.add(ticker)
            if len(normalized_candidates) >= max_scan_tickers:
                break

    if len(normalized_candidates) != len(raw_candidates):
        logger.warning(
            "macro_synthesis: repaired candidate list from %d to %d entries",
            len(raw_candidates),
            len(normalized_candidates[:max_scan_tickers]),
        )

    repaired["stocks_to_investigate"] = normalized_candidates[:max_scan_tickers]
    repaired["key_themes"] = list(repaired.get("key_themes") or [])
    repaired["risk_factors"] = list(repaired.get("risk_factors") or [])
    repaired["macro_context"] = dict(repaired.get("macro_context") or {})
    repaired["executive_summary"] = str(repaired.get("executive_summary") or "")
    return repaired


def create_macro_synthesis(
    llm: Any, max_scan_tickers: int = 10, scan_horizon_days: int = 30
) -> Callable[[ScannerState], dict[str, Any]]:
    def macro_synthesis_node(state: ScannerState) -> dict[str, Any]:
        scan_date, _run_id = require_scan_context(state, node_name="macro_synthesis")

        # 1. Idempotency Check
        existing_report = check_and_load_report(state, "macro_scan_summary")
        if existing_report:
            response = {
                "macro_scan_summary": existing_report,
                "sender": "macro_synthesis",
            }
            existing_regime_report = state.get("macro_regime_report")
            if existing_regime_report:
                response["macro_regime_report"] = existing_regime_report
            return response

        regime_data = classify_macro_regime(scan_date)
        canonical_regime = _canonical_regime_from_data(regime_data)
        macro_regime_report = format_macro_report(regime_data, report_date=scan_date)
        _validate_macro_regime_report(macro_regime_report, canonical_regime)
        save_node_report(state, "macro_regime_report", macro_regime_report)

        horizon_label = _format_horizon_label(scan_horizon_days)

        # Inject all previous reports for synthesis — keep it concise to avoid token bloat
        candidate_rankings = _build_candidate_rankings(state)
        ranking_section = ""
        if candidate_rankings:
            ranking_lines = [
                f"- {row['ticker']}: score={row['score']} sources={', '.join(row['sources'])}"
                for row in candidate_rankings
            ]
            ranking_section = "\n\n### Deterministic Rankings:\n" + "\n".join(ranking_lines)

        all_reports_context = f"""## Research Summaries
- Geo: {state.get("geopolitical_summary", "N/A")}
- Market: {state.get("market_movers_summary", "N/A")}
- Sector: {state.get("sector_summary", "N/A")}
- Factor: {state.get("factor_alignment_summary", "N/A")}
- Drift: {state.get("drift_opportunities_summary", "N/A")}
- Smart Money: {state.get("smart_money_summary", "N/A")}
- Industry Deep Dive: {state.get("industry_deep_dive_summary", "N/A")}
{ranking_section}
"""

        # Count usable vs unavailable sources for the synthesis prompt.
        _summary_keys = [
            "geopolitical_summary",
            "market_movers_summary",
            "sector_summary",
            "factor_alignment_summary",
            "drift_opportunities_summary",
            "smart_money_summary",
            "industry_deep_dive_summary",
        ]
        _usable = sum(
            1
            for k in _summary_keys
            if not (state.get(k, "") or "").startswith("[NO_EVIDENCE]") and state.get(k, "").strip()
        )
        _total = len(_summary_keys)

        system_message = (
            "You are a Senior Macro Strategist and Systems Architect synthesizing research into a clinical investment thesis. "
            "Your objective is to produce a data-dense macro summary and identify top-tier ticker candidates. "
            "STRICT CONSTRAINTS: Output ONLY valid JSON. NO preamble, NO conversational filler, and NO internal monologue or <think> tags. "
            "Do NOT include any 'thinking' process; provide only the final JSON result. "
            f"IMPORTANT: {_usable} of {_total} upstream sources provided usable evidence. "
            "Summaries marked [NO_EVIDENCE] are UNAVAILABLE — do NOT extract candidate tickers from them. "
            "Apply the 'Golden Overlap': prioritize Smart Money tickers that align with the top-down macro regime. "
            "Synthesize all evidence into a structured output following this schema: "
            "{\n"
            f'  "timeframe": "{horizon_label}",\n'
            '  "executive_summary": "... (approx. 100 - 150 words) ...",\n'
            '  "macro_context": { "economic_cycle": "... (approx. 40 - 50 words) ...", "central_bank_stance": "... (approx. 40 - 50 words) ...", "geopolitical_risks": ["... (approx. 20 - 30 words per item) ..."] },\n'
            '  "key_themes": [{ "theme": "...", "description": "... (approx. 40 - 60 words) ...", "conviction": "high|medium|low", "timeframe": "..." }],\n'
            '  "stocks_to_investigate": [{ "ticker": "...", "name": "...", "sector": "...", "rationale": "... (approx. 60 - 80 words) ...", '
            '"thesis_angle": "...", "conviction": "high|medium|low", "key_catalysts": ["..."], "risks": ["..."] }],\n'
            '  "risk_factors": ["... (approx. 30 - 40 words per item) ..."]\n'
            "}\n"
            f"{all_reports_context}"
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    " For your reference, the current date is {current_date}.",
                ),
                (
                    "human",
                    "Produce the final macro synthesis now as JSON only.",
                ),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names="none")
        prompt = prompt.partial(current_date=scan_date)

        chain = prompt | llm
        timeout_cap = float(DEFAULT_CONFIG.get("deep_think_llm_timeout_cap") or 360.0)
        timeout_seconds = min(
            float(
                DEFAULT_CONFIG.get("deep_think_llm_timeout")
                or DEFAULT_CONFIG.get("llm_timeout")
                or timeout_cap
            ),
            timeout_cap,
        )

        result, invoke_error = invoke_with_timeout(
            chain,
            {},
            timeout_seconds=timeout_seconds,
            max_tokens=DEFAULT_CONFIG.get("deep_think_llm_max_tokens"),
        )

        if invoke_error is not None:
            logger.error(
                "macro_synthesis invoke failed (%s): %s — aborting scan, no fallback.",
                type(invoke_error).__name__,
                invoke_error,
            )
            raise RuntimeError(
                f"Macro synthesis failed after {timeout_seconds:.0f}s "
                f"({type(invoke_error).__name__}). "
                "Scanner cannot proceed without candidate selection. "
                "Re-run or increase deep_think_llm_timeout and deep_think_llm_timeout_cap in config."
            ) from invoke_error

        report = str(getattr(result, "content", "") or "")
        result_message = result

        # Sanitize LLM output: strip markdown fences / <think> blocks before storing
        try:
            parsed = extract_json(report)
            parsed = _repair_macro_summary(parsed, state, max_scan_tickers, horizon_label)
            parsed["canonical_regime"] = canonical_regime
            report = json.dumps(parsed)
        except (ValueError, json.JSONDecodeError):
            # JSON extraction failed; strip think blocks from the raw string so that
            # internal monologue is not persisted or forwarded as downstream context.
            report = sanitize_llm_output(report)
            logger.warning(
                "macro_synthesis: could not extract JSON from LLM output; "
                "storing sanitized raw content (first 200 chars): %s",
                report[:200],
            )

        # 3. Resumability: Save after completion
        if report:
            save_node_report(state, "macro_scan_summary", report)

        return {
            "messages": [result_message],
            "macro_scan_summary": report,
            "macro_regime_report": macro_regime_report,
            "sender": "macro_synthesis",
        }

    return macro_synthesis_node
