import json
import logging

from tradingagents.agents.utils.json_utils import extract_json

logger = logging.getLogger(__name__)

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder


def create_macro_synthesis(llm):
    def macro_synthesis_node(state):
        scan_date = state["scan_date"]

        # Inject all previous reports for synthesis — no tools, pure LLM reasoning
        all_reports_context = f"""## All Scanner and Research Reports

### Geopolitical Report:
{state.get("geopolitical_report", "Not available")}

### Market Movers Report:
{state.get("market_movers_report", "Not available")}

### Sector Performance Report:
{state.get("sector_performance_report", "Not available")}

### Industry Deep Dive Report:
{state.get("industry_deep_dive_report", "Not available")}
"""

        system_message = (
            "You are a macro strategist synthesizing all scanner and research reports into a final investment thesis. "
            "You have received: geopolitical analysis, market movers analysis, sector performance analysis, "
            "and industry deep dive analysis. "
            "Synthesize these into a structured output with: "
            "(1) Executive summary of the macro environment, "
            "(2) Top macro themes with conviction levels, "
            "(3) A list of 8-10 specific stocks worth investigating with ticker, name, sector, rationale, "
            "thesis_angle (growth/value/catalyst/turnaround/defensive/momentum), conviction (high/medium/low), "
            "key_catalysts, and risks. "
            "Output your response as valid JSON matching this schema:\n"
            "{\n"
            '  "timeframe": "1 month",\n'
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
