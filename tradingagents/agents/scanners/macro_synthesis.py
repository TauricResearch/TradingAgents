import json
import logging
import re
from collections import defaultdict

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.json_utils import extract_json

logger = logging.getLogger(__name__)
_TICKER_RE = re.compile(r"\b[A-Z]{1,5}\b")
_TICKER_STOPWORDS = {
    "A", "I", "AI", "AN", "AND", "ARE", "AS", "AT", "BE", "BY", "END", "ETF",
    "GDP", "GICS", "JSON", "LOW", "NFP", "NOT", "NOW", "OIL", "ONLY", "OR",
    "THE", "TO", "USD", "VIX", "YTD", "CPI", "PPI", "EPS", "CEO", "CFO", "N/A",
}


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


def _build_candidate_rankings(state: dict, limit: int = 15) -> list[dict[str, object]]:
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


def create_macro_synthesis(llm, max_scan_tickers: int = 10, scan_horizon_days: int = 30):
    def macro_synthesis_node(state):
        scan_date = state["scan_date"]
        horizon_label = _format_horizon_label(scan_horizon_days)

        # Inject all previous reports for synthesis — no tools, pure LLM reasoning
        smart_money = state.get("smart_money_report", "") or "Not available"
        candidate_rankings = _build_candidate_rankings(state)
        ranking_section = ""
        if candidate_rankings:
            ranking_lines = [
                f"- {row['ticker']}: score={row['score']} sources={', '.join(row['sources'])}"
                for row in candidate_rankings
            ]
            ranking_section = "\n\n### Deterministic Candidate Ranking:\n" + "\n".join(ranking_lines)
        all_reports_context = f"""## All Scanner and Research Reports

### Geopolitical Report:
{state.get("geopolitical_report", "Not available")}

### Market Movers Report:
{state.get("market_movers_report", "Not available")}

### Sector Performance Report:
{state.get("sector_performance_report", "Not available")}

### Factor Alignment Report:
{state.get("factor_alignment_report", "Not available")}

### Drift Opportunities Report:
{state.get("drift_opportunities_report", "Not available")}

### Smart Money Report (Finviz institutional screeners):
{smart_money}

### Industry Deep Dive Report:
{state.get("industry_deep_dive_report", "Not available")}
{ranking_section}
"""

        system_message = (
            "You are a macro strategist synthesizing all scanner and research reports into a final investment thesis. "
            "You have received: geopolitical analysis, market movers analysis, sector performance analysis, "
            "smart money institutional screener results, and industry deep dive analysis. "
            "A deterministic candidate-ranking snapshot is also provided when available. Treat higher-ranked "
            "candidates as preferred because they appeared across more independent scanner streams. "
            "## THE GOLDEN OVERLAP (apply when Smart Money Report is available and not 'Not available'):\n"
            "Cross-reference the Smart Money tickers with your macro regime thesis. "
            "If a Smart Money ticker fits your top-down macro narrative (e.g., an Energy stock with heavy insider "
            "buying during an oil shortage), prioritize it as a top candidate and label its conviction as 'high'. "
            "If no Smart Money tickers fit the macro narrative, proceed with the best candidates from other reports.\n\n"
            "Synthesize all reports into a structured output with: "
            "(1) Executive summary of the macro environment, "
            "(2) Top macro themes with conviction levels, "
            f"(3) A list of exactly {max_scan_tickers} specific stocks worth investigating with ticker, name, sector, rationale, "
            "thesis_angle (growth/value/catalyst/turnaround/defensive/momentum), conviction (high/medium/low), "
            "key_catalysts, and risks. "
            "Output your response as valid JSON matching this schema:\n"
            "{\n"
            f'  "timeframe": "{horizon_label}",\n'
            '  "executive_summary": "...",\n'
            '  "macro_context": { "economic_cycle": "...", "central_bank_stance": "...", "geopolitical_risks": [...] },\n'
            '  "key_themes": [{ "theme": "...", "description": "...", "conviction": "high|medium|low", "timeframe": "..." }],\n'
            '  "stocks_to_investigate": [{ "ticker": "...", "name": "...", "sector": "...", "rationale": "...", '
            '"thesis_angle": "...", "conviction": "high|medium|low", "key_catalysts": [...], "risks": [...] }],\n'
            '  "risk_factors": ["..."]\n'
            "}"
            "\n\nIMPORTANT: Output ONLY valid JSON. Start your response with '{' and end with '}'. "
            "Do NOT use markdown code fences. Do NOT include any explanation or preamble before or after the JSON."
            f"\n\n{all_reports_context}"
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    " For your reference, the current date is {current_date}.",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names="none")
        prompt = prompt.partial(current_date=scan_date)

        chain = prompt | llm
        result = chain.invoke(state["messages"])

        report = result.content

        # Sanitize LLM output: strip markdown fences / <think> blocks before storing
        try:
            parsed = extract_json(report)
            report = json.dumps(parsed)
        except (ValueError, json.JSONDecodeError):
            logger.warning(
                "macro_synthesis: could not extract JSON from LLM output; "
                "storing raw content (first 200 chars): %s",
                report[:200],
            )

        return {
            "messages": [result],
            "macro_scan_summary": report,
            "sender": "macro_synthesis",
        }

    return macro_synthesis_node
