"""Transform final_state into structured JSON using GPT-5.3-Codex-High.

This module provides the transform_to_json() function that extracts structured
trading plan data from raw agent reports. The model is HARD-CODED to
gpt-5.3-codex-high — no user selection allowed.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, model_validator

logger = logging.getLogger(__name__)

# Hard-coded — no user selection
_TRANSFORM_PROVIDER: str = "openai"
_TRANSFORM_MODEL: str = "gpt-5.3-codex-high"
_MAX_RETRIES: int = 3
_RETRY_DELAYS: tuple[float, ...] = (1.0, 2.0, 4.0)

# Schema reference for LLM prompt
_SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "transform_flow.json"


# ---------------------------------------------------------------------------
# Pydantic models for ChartJSON schema
# ---------------------------------------------------------------------------


class ChartInfo(BaseModel):
    """Chart metadata and axis configuration."""

    title: str
    current_price: float
    y_axis_range: list[float] = Field(min_length=2, max_length=2)
    x_label: str = "Date"
    y_label: str = "Price (USDT)"


class PriceHistory(BaseModel):
    """Historical price data points."""

    dates: list[str] = Field(min_length=1)
    prices: list[float] = Field(min_length=1)

    @model_validator(mode="after")
    def _dates_prices_same_length(self) -> "PriceHistory":
        """Validate that dates and prices have the same length."""
        if len(self.dates) != len(self.prices):
            raise ValueError(
                f"dates ({len(self.dates)}) and prices ({len(self.prices)}) "
                f"must have equal length"
            )
        return self


class ReferenceLine(BaseModel):
    """A horizontal reference line on the chart (TP, SL, Entry, etc.)."""

    price: float
    label: str
    color: str = "gray"
    linestyle: str = "solid"
    linewidth: float = 1.0
    align: str = "right"


class ChartJSON(BaseModel):
    """Output schema from GPT-5.3-Codex-High — matches transform_flow.json."""

    chart_info: ChartInfo
    price_history: PriceHistory
    reference_lines: list[ReferenceLine] = Field(min_length=1)


# ---------------------------------------------------------------------------
# Transform function
# ---------------------------------------------------------------------------


def _load_schema_example() -> str:
    """Load the transform_flow.json schema as an example for the LLM."""
    try:
        with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning("Schema file not found at %s, using inline example", _SCHEMA_PATH)
        return json.dumps(
            {
                "chart_info": {
                    "title": "BTC/USDT Trading Plan (2026-04-26)",
                    "current_price": 78068.70,
                    "y_axis_range": [72000, 91000],
                    "x_label": "Date",
                    "y_label": "Price (USDT)",
                },
                "price_history": {
                    "dates": ["Apr 17", "Apr 18", "Apr 19", "Apr 20", "Apr 21"],
                    "prices": [77736, 75500, 73758, 76000, 77500],
                },
                "reference_lines": [
                    {"price": 89262, "label": "TP Max", "color": "green", "linestyle": "solid", "linewidth": 1.5, "align": "right"},
                    {"price": 78068, "label": "ENTRY (40%)", "color": "orange", "linestyle": "solid", "linewidth": 2.0, "align": "left"},
                    {"price": 76500, "label": "HARD SL", "color": "darkred", "linestyle": "dashdot", "linewidth": 2.0, "align": "right"},
                ],
            },
            indent=2,
        )


def _build_transform_prompt(final_state: dict, ticker: str, trade_date: str) -> str:
    """Build the user prompt for the transform LLM call."""
    schema_example = _load_schema_example()

    # Extract relevant sections from final_state with safe defaults
    market_report = final_state.get("market_report", "N/A")
    sentiment_report = final_state.get("sentiment_report", "N/A")
    news_report = final_state.get("news_report", "N/A")
    fundamentals_report = final_state.get("fundamentals_report", "N/A")

    debate = final_state.get("investment_debate_state", {})
    bull_history = debate.get("bull_history", "N/A")
    bear_history = debate.get("bear_history", "N/A")
    judge_decision = debate.get("judge_decision", "N/A")

    final_trade_decision = final_state.get("final_trade_decision", "N/A")

    return f"""Given the following trading analysis for {ticker} on {trade_date}:

## Market Report
{market_report}

## Sentiment Report
{sentiment_report}

## News Report
{news_report}

## Fundamentals Report
{fundamentals_report}

## Investment Debate
Bull: {bull_history}
Bear: {bear_history}
Judge: {judge_decision}

## Final Trade Decision
{final_trade_decision}

Output ONLY valid JSON, no markdown fences, no explanation. The JSON must follow this exact schema:
{schema_example}

Key rules:
- chart_info.title: Include ticker and date in English format, e.g. "BTC/USDT Trading Plan (2026-04-26)"
- chart_info.current_price: Extract from market report or final decision
- chart_info.y_axis_range: [min_price - 5%, max_price + 5%] to fit all reference lines
- price_history: Extract from market report data (last 7-10 trading days)
- reference_lines: Extract ALL price levels mentioned in final_trade_decision:
  - Take Profit levels (TP) → color: "green"
  - Entry levels → color: "orange"
  - Breakout/Add levels → color: "blue"
  - Stop Loss levels (SL) → color: "darkred"
  - Short entry/TP levels → color: "red"
  - Caution/reduce levels → color: "darkorange"
"""


def _parse_llm_response(response_content: str) -> ChartJSON:
    """Parse LLM response content into ChartJSON, handling common issues."""
    content = response_content.strip()

    # Remove markdown code fences if present
    if content.startswith("```"):
        lines = content.split("\n")
        # Remove first line (```json or ```) and last line (```)
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    # Parse JSON
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON from LLM: {e}") from e

    # Validate against ChartJSON schema
    return ChartJSON.model_validate(data)


def transform_to_json(
    final_state: dict,
    ticker: str,
    trade_date: str,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
) -> ChartJSON:
    """Transform raw final_state into structured JSON using GPT-5.3-Codex-High.

    This function ALWAYS uses gpt-5.3-codex-high regardless of the user's
    CLI model selection. The model is hard-coded by design.

    Output JSON conforms to docs/transform_flow.json schema:
    - chart_info: title, current_price, y_axis_range
    - price_history: dates[], prices[]
    - reference_lines[]: price levels (TP, SL, Entry, etc.)

    Args:
        final_state: Complete state dict from graph execution.
        ticker: Trading symbol (e.g. "AAPL", "BTCUSDT").
        trade_date: Analysis date in YYYY-MM-DD.
        base_url: Optional OpenAI-compatible base URL override.
        api_key: Optional API key override (default: OPENAI_API_KEY env).

    Returns:
        ChartJSON validated against transform_flow.json schema.

    Raises:
        EnvironmentError: If OPENAI_API_KEY is not set.
        RuntimeError: If LLM call fails after retries.
        ValueError: If LLM output doesn't match ChartJSON schema.
    """
    # Check for API key
    effective_api_key = api_key or os.environ.get("OPENAI_API_KEY")
    if not effective_api_key:
        raise EnvironmentError(
            "OPENAI_API_KEY not set. Cannot run transform_to_json(). "
            "Set the environment variable or pass api_key parameter."
        )

    # Import here to avoid heavy import at module load
    from tradingagents.llm_clients import create_llm_client

    # Create LLM client with hard-coded model
    client = create_llm_client(
        provider=_TRANSFORM_PROVIDER,
        model=_TRANSFORM_MODEL,
        base_url=base_url,
        api_key=effective_api_key,
    )
    llm = client.get_llm()

    # Build prompt with embedded JSON schema
    json_schema = ChartJSON.model_json_schema()
    
    system_prompt = f"""You are a financial data extraction engine.
Extract trading plan data into the EXACT JSON schema below.

JSON SCHEMA (follow field names, types, and nesting EXACTLY):
{json.dumps(json_schema, indent=2)}

RULES:
1. Output ONLY valid JSON. No markdown, no explanation.
2. Every field is REQUIRED unless marked optional.
3. reference_lines: extract ALL price levels from the trading decision.
   Color mapping:
   - Take Profit (TP) → "green"
   - Entry → "orange"
   - Breakout/Add → "blue"
   - Stop Loss (SL) → "darkred"
   - Short entry/TP → "red"
   - Caution/Reduce → "darkorange"
4. price_history.dates and price_history.prices must be same length.
5. y_axis_range: [lowest_reference_line - 5%, highest_reference_line + 5%]
"""
    user_prompt = _build_transform_prompt(final_state, ticker, trade_date)

    # Retry loop with exponential backoff
    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]

            # Try structured output for OpenAI (gpt-5.3-codex-high)
            # This enforces JSON schema compliance
            try:
                response = llm.invoke(
                    messages,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "ChartJSON",
                            "strict": True,
                            "schema": json_schema,
                        },
                    },
                )
            except (NotImplementedError, TypeError, ValueError) as e:
                # Fallback: provider doesn't support response_format
                logger.debug("response_format not supported, using prompt-only mode: %s", e)
                response = llm.invoke(messages)
            
            response_content = response.content

            # Parse and validate
            chart_json = _parse_llm_response(response_content)

            logger.info(
                "Successfully transformed final_state to ChartJSON for %s on %s",
                ticker,
                trade_date,
            )
            return chart_json

        except json.JSONDecodeError as e:
            last_error = e
            logger.warning(
                "Attempt %d/%d: LLM returned invalid JSON: %s",
                attempt + 1,
                _MAX_RETRIES,
                e,
            )
        except ValidationError as e:
            last_error = ValueError(f"LLM output doesn't match ChartJSON schema: {e}")
            logger.warning(
                "Attempt %d/%d: Schema validation failed: %s",
                attempt + 1,
                _MAX_RETRIES,
                e,
            )
        except Exception as e:
            # Check for transient errors (rate limits, server errors)
            error_str = str(e).lower()
            is_transient = any(
                code in error_str
                for code in ("429", "500", "503", "rate limit", "overloaded")
            )

            if is_transient and attempt < _MAX_RETRIES - 1:
                delay = _RETRY_DELAYS[attempt]
                logger.info(
                    "Attempt %d/%d: Transient error, retrying in %.1fs: %s",
                    attempt + 1,
                    _MAX_RETRIES,
                    delay,
                    e,
                )
                time.sleep(delay)
                continue

            last_error = e
            logger.error("LLM call failed: %s", e)

        # Retry delay for non-transient errors
        if attempt < _MAX_RETRIES - 1:
            delay = _RETRY_DELAYS[attempt]
            time.sleep(delay)

    raise RuntimeError(
        f"transform_to_json() failed after {_MAX_RETRIES} retries: {last_error}"
    )
