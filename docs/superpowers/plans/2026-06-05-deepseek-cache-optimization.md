# DeepSeek Cache Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve TradingAgents' DeepSeek official API cache hit ratio and reduce cache-miss tokens by making investment-team prompts byte-stable at the prefix and dynamic only at the user-tail.

**Architecture:** Add a small prompt-cache utility module for deterministic dynamic sections, trimming, budgets, and static-prefix fingerprints. Refactor investment-team agents to expose pure prompt-builder functions that tests can inspect without network calls, then extend cache telemetry reporting and add an optional DeepSeek warm-up script. No gateway-only cache controls are introduced.

**Tech Stack:** Python 3.10+, LangChain `ChatPromptTemplate`, LangGraph, pytest, SQLite-backed persistence, DeepSeek OpenAI-compatible chat API through existing `OpenAIClient`.

---

## File Structure

- Create `tradingagents/agents/utils/prompt_cache.py`: deterministic prompt-tail builder, trimming helpers, config budget lookup, and static-prefix fingerprinting for tests.
- Create `tests/agents/test_prompt_cache_utils.py`: unit tests for the prompt-cache helper module.
- Modify `tradingagents/default_config.py`: add prompt cache budget defaults.
- Create `tests/test_prompt_cache_config.py`: unit tests for default prompt-cache budget keys.
- Modify `tradingagents/agents/analysts/sentiment_analyst.py`: move source methodology to a static system constant and source data to a deterministic user-tail builder.
- Modify `tradingagents/agents/analysts/derivative_analyst.py`: move date and instrument context out of the system message.
- Modify `tradingagents/agents/analysts/market_analyst.py`: expose static prompt and dynamic user-tail builders while preserving tool behavior.
- Modify `tradingagents/agents/analysts/news_analyst.py`: expose static prompt and dynamic user-tail builders while preserving tool behavior.
- Modify `tradingagents/agents/analysts/fundamentals_analyst.py`: expose static prompt and dynamic user-tail builders while preserving tool behavior.
- Create `tests/agents/test_analyst_prompt_prefixes.py`: unit tests for analyst static-prefix determinism.
- Modify `tradingagents/agents/researchers/bull_researcher.py`: static system prompt and deterministic report/debate user-tail.
- Modify `tradingagents/agents/researchers/bear_researcher.py`: static system prompt and deterministic report/debate user-tail.
- Modify `tradingagents/agents/risk_mgmt/aggressive_debator.py`: static system prompt and deterministic report/debate user-tail.
- Modify `tradingagents/agents/risk_mgmt/conservative_debator.py`: static system prompt and deterministic report/debate user-tail.
- Modify `tradingagents/agents/risk_mgmt/neutral_debator.py`: static system prompt and deterministic report/debate user-tail.
- Create `tests/agents/test_debate_prompt_prefixes.py`: unit tests for debate/risk static-prefix determinism and tail budgets.
- Modify `tradingagents/agents/managers/research_manager.py`: static system prompt and deterministic debate/prior-pack user-tail.
- Modify `tradingagents/agents/trader/trader.py`: static system prompt and deterministic investment-plan/prior-pack user-tail.
- Modify `tradingagents/agents/managers/portfolio_manager.py`: static system prompt and deterministic risk/memory/prior-pack user-tail.
- Modify `tests/test_structured_agents.py`: assert structured-agent prompt prefixes stay stable when ticker/date changes.
- Modify `tests/test_memory_log.py`: keep portfolio manager memory injection assertions aligned with the new tail marker.
- Modify `tradingagents/dashboard/panels/costs.py`: aggregate cache hit/miss tokens and cache-hit ratio.
- Modify `tests/dashboard/test_costs_panel.py`: unit tests for cache ratio aggregation.
- Create `scripts/warm_deepseek_prompt_cache.py`: optional DeepSeek official API prompt warm-up command with dry-run.
- Create `tests/scripts/test_warm_deepseek_prompt_cache.py`: dry-run and prompt-family tests for the warm-up script.

---

## Task 1: Prompt Cache Helper

**Files:**
- Create: `tradingagents/agents/utils/prompt_cache.py`
- Create: `tests/agents/test_prompt_cache_utils.py`

- [ ] **Step 1: Write failing utility tests**

Create `tests/agents/test_prompt_cache_utils.py`:

```python
import pytest

from tradingagents.agents.utils.prompt_cache import (
    DYNAMIC_CONTEXT_MARKER,
    get_prompt_cache_budget,
    prompt_prefix_fingerprint,
    stable_join_sections,
    trim_context_block,
)


def test_stable_join_sections_keeps_order_and_skips_empty():
    text = stable_join_sections(
        [
            ("Trade Date", "2026-06-05"),
            ("Empty", ""),
            ("Ticker", "NVDA"),
            ("None", None),
        ]
    )

    assert text == (
        f"{DYNAMIC_CONTEXT_MARKER}\n\n"
        "### Trade Date\n"
        "2026-06-05\n\n"
        "### Ticker\n"
        "NVDA"
    )


def test_trim_context_block_keeps_short_text_unchanged():
    assert trim_context_block("abc", 10, "sample") == "abc"


def test_trim_context_block_keeps_recent_tail_deterministically():
    text = "0123456789"

    assert trim_context_block(text, 4, "debate") == (
        "[truncated debate: kept most recent 4 chars]\n6789"
    )


def test_trim_context_block_rejects_non_positive_budget():
    with pytest.raises(ValueError, match="max_chars must be positive"):
        trim_context_block("abc", 0, "bad")


def test_prompt_prefix_fingerprint_ignores_dynamic_tail():
    messages_a = [
        {"role": "system", "content": "static instructions"},
        {"role": "user", "content": f"{DYNAMIC_CONTEXT_MARKER}\n\n### Ticker\nNVDA"},
    ]
    messages_b = [
        {"role": "system", "content": "static instructions"},
        {"role": "user", "content": f"{DYNAMIC_CONTEXT_MARKER}\n\n### Ticker\nAAPL"},
    ]

    assert prompt_prefix_fingerprint(messages_a) == prompt_prefix_fingerprint(messages_b)


def test_prompt_prefix_fingerprint_changes_when_static_prefix_changes():
    messages_a = [{"role": "system", "content": "static instructions"}]
    messages_b = [{"role": "system", "content": "changed instructions"}]

    assert prompt_prefix_fingerprint(messages_a) != prompt_prefix_fingerprint(messages_b)


def test_get_prompt_cache_budget_reads_config(monkeypatch):
    import tradingagents.agents.utils.prompt_cache as mod

    monkeypatch.setattr(
        mod,
        "get_config",
        lambda: {"prompt_cache_report_budget_chars": "1234"},
    )

    assert get_prompt_cache_budget("prompt_cache_report_budget_chars", 5000) == 1234
```

- [ ] **Step 2: Run utility tests to verify failure**

Run: `pytest tests/agents/test_prompt_cache_utils.py -v`

Expected: FAIL during import with `ModuleNotFoundError: No module named 'tradingagents.agents.utils.prompt_cache'`.

- [ ] **Step 3: Implement prompt cache helper**

Create `tradingagents/agents/utils/prompt_cache.py`:

```python
"""Prompt helpers for DeepSeek official API context-cache friendliness.

DeepSeek caches overlapping prompt prefixes automatically. These helpers keep
static instructions byte-stable and push run-specific data behind one dynamic
marker so tests can assert prefix stability without calling the API.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Sequence, Tuple

from tradingagents.dataflows.config import get_config


DYNAMIC_CONTEXT_MARKER = "## Dynamic Run Context"


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def stable_join_sections(
    sections: Iterable[Tuple[str, Any]],
    *,
    marker: str = DYNAMIC_CONTEXT_MARKER,
) -> str:
    """Render dynamic prompt sections in caller-provided order.

    Empty bodies are skipped, but present sections are never re-ordered.
    """
    parts = [marker]
    for title, body in sections:
        text = _clean_text(body)
        if not text:
            continue
        parts.append(f"### {title}\n{text}")
    return "\n\n".join(parts).rstrip()


def trim_context_block(text: Any, max_chars: int, label: str) -> str:
    """Keep the most recent characters of a dynamic block with a stable marker."""
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    value = _clean_text(text)
    if len(value) <= max_chars:
        return value
    return f"[truncated {label}: kept most recent {max_chars} chars]\n{value[-max_chars:]}"


def get_prompt_cache_budget(key: str, default: int) -> int:
    """Read an integer budget from runtime config with a deterministic fallback."""
    raw = get_config().get(key, default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def budgeted_dynamic_text(text: Any, key: str, default: int, label: str) -> str:
    return trim_context_block(text, get_prompt_cache_budget(key, default), label)


def _message_role_and_content(message: Any) -> tuple[str, str]:
    if isinstance(message, dict):
        return str(message.get("role", "")), str(message.get("content", ""))
    if isinstance(message, tuple) and len(message) >= 2:
        return str(message[0]), str(message[1])
    role = getattr(message, "role", None) or getattr(message, "type", "")
    content = getattr(message, "content", "")
    return str(role), str(content)


def prompt_prefix_fingerprint(
    messages: Sequence[Any],
    *,
    dynamic_start_marker: str = DYNAMIC_CONTEXT_MARKER,
) -> str:
    """Hash only the static prefix before the dynamic context marker."""
    prefix_parts: list[dict[str, str]] = []
    for message in messages:
        role, content = _message_role_and_content(message)
        marker_index = content.find(dynamic_start_marker)
        if marker_index >= 0:
            prefix_parts.append({"role": role, "content": content[:marker_index]})
            break
        prefix_parts.append({"role": role, "content": content})
    payload = json.dumps(prefix_parts, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Run utility tests to verify pass**

Run: `pytest tests/agents/test_prompt_cache_utils.py -v`

Expected: PASS, 7 tests.

- [ ] **Step 5: Commit helper**

```bash
git add tradingagents/agents/utils/prompt_cache.py tests/agents/test_prompt_cache_utils.py
git commit -m "feat(prompts): add DeepSeek cache prompt helpers"
```

---

## Task 2: Prompt Cache Budget Defaults

**Files:**
- Modify: `tradingagents/default_config.py`
- Create: `tests/test_prompt_cache_config.py`

- [ ] **Step 1: Write failing config tests**

Create `tests/test_prompt_cache_config.py`:

```python
from tradingagents.default_config import DEFAULT_CONFIG


def test_prompt_cache_budget_defaults_present():
    assert DEFAULT_CONFIG["prompt_cache_dynamic_budget_chars"] == 24000
    assert DEFAULT_CONFIG["prompt_cache_report_budget_chars"] == 5000
    assert DEFAULT_CONFIG["prompt_cache_debate_budget_chars"] == 8000
    assert DEFAULT_CONFIG["prompt_cache_prior_pack_budget_chars"] == 8000
    assert DEFAULT_CONFIG["prompt_cache_memory_budget_chars"] == 6000
```

- [ ] **Step 2: Run config test to verify failure**

Run: `pytest tests/test_prompt_cache_config.py -v`

Expected: FAIL with `KeyError: 'prompt_cache_dynamic_budget_chars'`.

- [ ] **Step 3: Add defaults**

In `tradingagents/default_config.py`, insert these keys in `DEFAULT_CONFIG` near the LLM settings block before `"llm_provider"`:

```python
    # DeepSeek official API prompt-cache optimization. These budgets cap only
    # dynamic tail content; static instructions are never trimmed.
    "prompt_cache_dynamic_budget_chars": 24000,
    "prompt_cache_report_budget_chars": 5000,
    "prompt_cache_debate_budget_chars": 8000,
    "prompt_cache_prior_pack_budget_chars": 8000,
    "prompt_cache_memory_budget_chars": 6000,
```

- [ ] **Step 4: Run config test to verify pass**

Run: `pytest tests/test_prompt_cache_config.py -v`

Expected: PASS, 1 test.

- [ ] **Step 5: Commit config defaults**

```bash
git add tradingagents/default_config.py tests/test_prompt_cache_config.py
git commit -m "config: add prompt cache budget defaults"
```

---

## Task 3: Sentiment and Derivatives Prompt Builders

**Files:**
- Modify: `tradingagents/agents/analysts/sentiment_analyst.py`
- Modify: `tradingagents/agents/analysts/derivative_analyst.py`
- Create: `tests/agents/test_analyst_prompt_prefixes.py`

- [ ] **Step 1: Write failing tests for sentiment and derivatives prefix stability**

Create `tests/agents/test_analyst_prompt_prefixes.py`:

```python
from tradingagents.agents.analysts.derivative_analyst import (
    DERIVATIVES_SYSTEM_MESSAGE,
    build_derivatives_user_prompt,
)
from tradingagents.agents.analysts.sentiment_analyst import (
    SENTIMENT_SYSTEM_MESSAGE,
    build_sentiment_user_prompt,
)
from tradingagents.agents.utils.agent_utils import build_instrument_context
from tradingagents.agents.utils.prompt_cache import DYNAMIC_CONTEXT_MARKER, prompt_prefix_fingerprint


def test_sentiment_static_prefix_ignores_ticker_date_and_source_blocks():
    messages_a = [
        {"role": "system", "content": SENTIMENT_SYSTEM_MESSAGE},
        {
            "role": "user",
            "content": build_sentiment_user_prompt(
                ticker="NVDA",
                instrument_context=build_instrument_context("NVDA"),
                start_date="2026-05-29",
                end_date="2026-06-05",
                news_block="NVDA news",
                stocktwits_block="NVDA stocktwits",
                reddit_block="NVDA reddit",
            ),
        },
    ]
    messages_b = [
        {"role": "system", "content": SENTIMENT_SYSTEM_MESSAGE},
        {
            "role": "user",
            "content": build_sentiment_user_prompt(
                ticker="AAPL",
                instrument_context=build_instrument_context("AAPL"),
                start_date="2026-05-28",
                end_date="2026-06-04",
                news_block="AAPL news",
                stocktwits_block="AAPL stocktwits",
                reddit_block="AAPL reddit",
            ),
        },
    ]

    assert prompt_prefix_fingerprint(messages_a) == prompt_prefix_fingerprint(messages_b)
    assert DYNAMIC_CONTEXT_MARKER in messages_a[1]["content"]
    assert "NVDA news" in messages_a[1]["content"]
    assert "NVDA" not in SENTIMENT_SYSTEM_MESSAGE
    assert "2026" not in SENTIMENT_SYSTEM_MESSAGE


def test_derivatives_system_message_has_no_dynamic_context():
    user_prompt = build_derivatives_user_prompt(
        current_date="2026-06-05",
        instrument_context=build_instrument_context("NVDA"),
    )

    assert "2026-06-05" not in DERIVATIVES_SYSTEM_MESSAGE
    assert "NVDA" not in DERIVATIVES_SYSTEM_MESSAGE
    assert DYNAMIC_CONTEXT_MARKER in user_prompt
    assert "2026-06-05" in user_prompt
    assert "NVDA" in user_prompt
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/agents/test_analyst_prompt_prefixes.py -v`

Expected: FAIL with import errors for `SENTIMENT_SYSTEM_MESSAGE` and `DERIVATIVES_SYSTEM_MESSAGE`.

- [ ] **Step 3: Refactor sentiment prompt**

In `tradingagents/agents/analysts/sentiment_analyst.py`, add imports:

```python
from tradingagents.agents.utils.prompt_cache import (
    budgeted_dynamic_text,
    stable_join_sections,
)
```

Replace `_build_system_message` with this static constant and builder:

```python
SENTIMENT_SYSTEM_MESSAGE = """You are a financial market sentiment analyst. Your task is to produce a comprehensive sentiment report for the instrument using three complementary data sources that have already been collected for you.

## Data sources

### News headlines — Yahoo Finance, past 7 days
Institutional framing. Fact-driven, slower-moving signal.

### StockTwits messages — retail-trader social platform indexed by cashtag
Fast-moving signal. Each message carries a user-labeled sentiment tag (Bullish / Bearish / no-label) plus the message body.

### Reddit posts — r/wallstreetbets, r/stocks, r/investing
Community discussion. Engagement signal via upvote score and comment count. Subreddit character matters: r/wallstreetbets is often contrarian or exuberant; r/stocks is more measured; r/investing is longer-term.

## How to analyze this data

1. Read the StockTwits Bullish/Bearish ratio as a leading retail-sentiment signal. A 70/30 bullish/bearish split is moderately bullish; 90/10 or higher may indicate over-extension and contrarian risk; 50/50 is uncertainty. Sample size matters.
2. Look for cross-source divergences. If news framing is bearish but StockTwits is overwhelmingly bullish, that mismatch is itself a signal.
3. Weight Reddit posts by engagement. A highly engaged thread reflects community attention; a low-engagement post is noise.
4. Distinguish opinion from event. News headlines are events; social posts are opinions.
5. Identify recurring narrative themes across sources.
6. Be honest about data limits. If a source is unavailable or thin, say so explicitly.
7. Identify catalysts and risks surfaced by the data.
8. Past sentiment is not predictive. Frame conclusions as a signal for the trader to weigh alongside fundamentals and technicals.

## Output

Produce a sentiment report covering, in order:

1. Overall sentiment direction: Bullish, Bearish, Neutral, or Mixed, with a confidence note based on data quality and sample size.
2. Source-by-source breakdown with specific evidence.
3. Divergences, alignments, and key narratives across sources.
4. Catalysts and risks surfaced by the data.
5. A Markdown table summarizing key sentiment signals, direction, source, and supporting evidence."""


def build_sentiment_user_prompt(
    *,
    ticker: str,
    instrument_context: str,
    start_date: str,
    end_date: str,
    news_block: str,
    stocktwits_block: str,
    reddit_block: str,
) -> str:
    return stable_join_sections(
        [
            ("Ticker", ticker),
            ("Instrument Context", instrument_context),
            ("Sentiment Window", f"{start_date} to {end_date}"),
            (
                "News Headlines - Yahoo Finance",
                budgeted_dynamic_text(
                    news_block,
                    "prompt_cache_report_budget_chars",
                    5000,
                    "sentiment news",
                ),
            ),
            (
                "StockTwits Messages",
                budgeted_dynamic_text(
                    stocktwits_block,
                    "prompt_cache_report_budget_chars",
                    5000,
                    "stocktwits messages",
                ),
            ),
            (
                "Reddit Posts",
                budgeted_dynamic_text(
                    reddit_block,
                    "prompt_cache_report_budget_chars",
                    5000,
                    "reddit posts",
                ),
            ),
            (
                "Current Task",
                "Produce the sentiment report using the static methodology and the dynamic source blocks above.",
            ),
        ]
    )
```

Inside `sentiment_analyst_node`, replace the `_build_system_message` call with:

```python
        system_message = apply_fragment(
            SENTIMENT_SYSTEM_MESSAGE + get_language_instruction(),
            persona,
        )
        user_prompt = build_sentiment_user_prompt(
            ticker=ticker,
            instrument_context=instrument_context,
            start_date=start_date,
            end_date=end_date,
            news_block=news_block,
            stocktwits_block=stocktwits_block,
            reddit_block=reddit_block,
        )
```

Then change the prompt human template to:

```python
                (
                    "human",
                    "{user_prompt}",
                ),
```

And replace `prompt.partial(system_message=system_message)` plus current date/instrument partials with:

```python
        prompt = prompt.partial(user_prompt=user_prompt)
```

Keep the existing collaboration system message and `MessagesPlaceholder`.

- [ ] **Step 4: Refactor derivatives prompt**

In `tradingagents/agents/analysts/derivative_analyst.py`, import:

```python
from tradingagents.agents.utils.prompt_cache import stable_join_sections
```

Add these definitions near the imports:

```python
DERIVATIVES_SYSTEM_MESSAGE = (
    "You are a derivatives analyst. Analyze the options market for the instrument and "
    "explain what it implies for the underlying. Start with get_options_overview to frame "
    "expirations, implied volatility, and the put/call open-interest ratio, then pull "
    "get_options_chain for the nearest and one further expiry to inspect skew, liquidity, "
    "and notable strikes. Cover: (1) implied volatility level and term structure, "
    "(2) skew between put and call IV and what it says about hedging or positioning, "
    "(3) unusual volume or open-interest concentrations, "
    "(4) one or two concrete derivatives strategies an investor could consider with the "
    "directional thesis each expresses, and (5) the key risks: assignment, theta, and "
    "IV crush around events. Be specific and actionable; do not give generic options education. "
    "Append a Markdown table at the end summarizing key levels, IV, and strategies."
)


def build_derivatives_user_prompt(*, current_date: str, instrument_context: str) -> str:
    return stable_join_sections(
        [
            ("Trade Date", current_date),
            ("Instrument Context", instrument_context),
            (
                "Current Task",
                "Use the available derivatives tools to produce the options-market report.",
            ),
        ]
    )
```

Inside `derivative_analyst_node`, replace the local system-message construction block with:

```python
        system_message = apply_fragment(
            DERIVATIVES_SYSTEM_MESSAGE + get_language_instruction(),
            persona,
        )
        user_prompt = build_derivatives_user_prompt(
            current_date=current_date,
            instrument_context=instrument_context,
        )
```

Change the prompt messages to:

```python
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " You have access to the following tools: {tool_names}.\n{system_message}",
                ),
                ("human", "{user_prompt}"),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )
```

Add `prompt = prompt.partial(user_prompt=user_prompt)` with the existing partial calls.

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest tests/agents/test_analyst_prompt_prefixes.py -v`

Expected: PASS, 2 tests.

- [ ] **Step 6: Run existing sentiment and graph smoke-adjacent tests**

Run: `pytest tests/test_structured_agents.py tests/graph/test_mandatory_derivatives_reverted.py -v`

Expected: PASS.

- [ ] **Step 7: Commit sentiment and derivatives refactor**

```bash
git add tradingagents/agents/analysts/sentiment_analyst.py tradingagents/agents/analysts/derivative_analyst.py tests/agents/test_analyst_prompt_prefixes.py
git commit -m "refactor(prompts): stabilize sentiment and derivatives prefixes"
```

---

## Task 4: Market, News, and Fundamentals Prompt Builders

**Files:**
- Modify: `tradingagents/agents/analysts/market_analyst.py`
- Modify: `tradingagents/agents/analysts/news_analyst.py`
- Modify: `tradingagents/agents/analysts/fundamentals_analyst.py`
- Modify: `tests/agents/test_analyst_prompt_prefixes.py`

- [ ] **Step 1: Add failing tests for remaining analyst builders**

Append to `tests/agents/test_analyst_prompt_prefixes.py`:

```python
from tradingagents.agents.analysts.fundamentals_analyst import (
    FUNDAMENTALS_SYSTEM_MESSAGE,
    build_fundamentals_user_prompt,
)
from tradingagents.agents.analysts.market_analyst import (
    MARKET_SYSTEM_MESSAGE,
    build_market_user_prompt,
)
from tradingagents.agents.analysts.news_analyst import (
    NEWS_SYSTEM_MESSAGE,
    build_news_user_prompt,
)


def test_market_news_and_fundamentals_static_prompts_do_not_contain_run_values():
    dynamic_values = ("NVDA", "AAPL", "2026-06-05")
    for system_message in (
        MARKET_SYSTEM_MESSAGE,
        NEWS_SYSTEM_MESSAGE,
        FUNDAMENTALS_SYSTEM_MESSAGE,
    ):
        for value in dynamic_values:
            assert value not in system_message


def test_market_user_prompt_places_snapshot_after_dynamic_marker():
    user_prompt = build_market_user_prompt(
        current_date="2026-06-05",
        instrument_context=build_instrument_context("NVDA"),
        market_snapshot_context="snapshot body",
    )

    assert user_prompt.startswith(DYNAMIC_CONTEXT_MARKER)
    assert "2026-06-05" in user_prompt
    assert "NVDA" in user_prompt
    assert "snapshot body" in user_prompt


def test_news_and_fundamentals_user_prompts_place_dynamic_context_in_tail():
    news_prompt = build_news_user_prompt(
        current_date="2026-06-05",
        instrument_context=build_instrument_context("NVDA"),
    )
    fundamentals_prompt = build_fundamentals_user_prompt(
        current_date="2026-06-05",
        instrument_context=build_instrument_context("NVDA"),
    )

    assert news_prompt.startswith(DYNAMIC_CONTEXT_MARKER)
    assert fundamentals_prompt.startswith(DYNAMIC_CONTEXT_MARKER)
    assert "NVDA" in news_prompt
    assert "NVDA" in fundamentals_prompt
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/agents/test_analyst_prompt_prefixes.py -v`

Expected: FAIL with import errors for `MARKET_SYSTEM_MESSAGE`, `NEWS_SYSTEM_MESSAGE`, or `FUNDAMENTALS_SYSTEM_MESSAGE`.

- [ ] **Step 3: Refactor market analyst prompt into constants and user builder**

In `tradingagents/agents/analysts/market_analyst.py`, import `stable_join_sections`:

```python
from tradingagents.agents.utils.prompt_cache import stable_join_sections
```

Move the existing long market instruction text into a module-level constant named `MARKET_SYSTEM_MESSAGE`. Keep the indicator list and output instructions exactly as they are today, but remove `+ get_language_instruction()` from the constant.

Add this builder:

```python
def build_market_user_prompt(
    *,
    current_date: str,
    instrument_context: str,
    market_snapshot_context: str,
) -> str:
    return stable_join_sections(
        [
            ("Trade Date", current_date),
            ("Instrument Context", instrument_context),
            ("Pre-Fetched Numerical Market Snapshot", market_snapshot_context),
            (
                "Current Task",
                "Use the available market tools when needed and produce the market report.",
            ),
        ]
    )
```

Inside `market_analyst_node`, replace the local system-message construction expression with:

```python
        system_message = apply_fragment(
            MARKET_SYSTEM_MESSAGE + get_language_instruction(),
            persona,
        )
        user_prompt = build_market_user_prompt(
            current_date=current_date,
            instrument_context=instrument_context,
            market_snapshot_context=market_snapshot_context,
        )
```

Change the human template to `("human", "{user_prompt}")` and partial `user_prompt=user_prompt`.

- [ ] **Step 4: Refactor news analyst prompt into constants and user builder**

In `tradingagents/agents/analysts/news_analyst.py`, import `stable_join_sections`:

```python
from tradingagents.agents.utils.prompt_cache import stable_join_sections
```

Add this static prompt:

```python
NEWS_SYSTEM_MESSAGE = (
    "You are a news researcher tasked with analyzing recent news and trends over the past week. "
    "Write a comprehensive report of the current state of the world that is relevant for trading "
    "and macroeconomics. Use the available tools: get_news(query, start_date, end_date) for "
    "instrument-specific or targeted news searches, and get_global_news(curr_date, look_back_days, "
    "limit) for broader macroeconomic news. Provide specific, actionable insights with supporting "
    "evidence to help traders make informed decisions. Append a Markdown table at the end of the "
    "report to organize key points."
)
```

Add this builder:

```python
def build_news_user_prompt(*, current_date: str, instrument_context: str) -> str:
    return stable_join_sections(
        [
            ("Trade Date", current_date),
            ("Instrument Context", instrument_context),
            (
                "Current Task",
                "Use targeted and global news tools to produce the news and macro report.",
            ),
        ]
    )
```

Inside `news_analyst_node`, set:

```python
        system_message = apply_fragment(
            NEWS_SYSTEM_MESSAGE + get_language_instruction(),
            persona,
        )
        user_prompt = build_news_user_prompt(
            current_date=current_date,
            instrument_context=instrument_context,
        )
```

Change the human template to `("human", "{user_prompt}")` and partial `user_prompt=user_prompt`.

- [ ] **Step 5: Refactor fundamentals analyst prompt into constants and user builder**

In `tradingagents/agents/analysts/fundamentals_analyst.py`, import `stable_join_sections`:

```python
from tradingagents.agents.utils.prompt_cache import stable_join_sections
```

Add this static prompt:

```python
FUNDAMENTALS_SYSTEM_MESSAGE = (
    "You are a researcher tasked with analyzing fundamental information over the past week about "
    "the instrument. Write a comprehensive report covering financial documents, profile, basic "
    "financials, and financial history to inform traders. Include as much detail as the data "
    "supports. Provide specific, actionable insights with supporting evidence. Append a Markdown "
    "table at the end of the report to organize key points. Use the available tools: "
    "get_fundamentals for comprehensive analysis, get_balance_sheet, get_cashflow, and "
    "get_income_statement for specific financial statements."
)
```

Add this builder:

```python
def build_fundamentals_user_prompt(*, current_date: str, instrument_context: str) -> str:
    return stable_join_sections(
        [
            ("Trade Date", current_date),
            ("Instrument Context", instrument_context),
            (
                "Current Task",
                "Use the available fundamentals tools to produce the fundamentals report.",
            ),
        ]
    )
```

Inside `fundamentals_analyst_node`, set:

```python
        system_message = apply_fragment(
            FUNDAMENTALS_SYSTEM_MESSAGE + get_language_instruction(),
            persona,
        )
        user_prompt = build_fundamentals_user_prompt(
            current_date=current_date,
            instrument_context=instrument_context,
        )
```

Change the human template to `("human", "{user_prompt}")` and partial `user_prompt=user_prompt`.

- [ ] **Step 6: Run analyst prompt tests**

Run: `pytest tests/agents/test_analyst_prompt_prefixes.py -v`

Expected: PASS, all analyst prompt tests.

- [ ] **Step 7: Run analyst execution and structured tests**

Run: `pytest tests/test_analyst_execution.py tests/test_structured_agents.py -v`

Expected: PASS.

- [ ] **Step 8: Commit analyst prompt builders**

```bash
git add tradingagents/agents/analysts/market_analyst.py tradingagents/agents/analysts/news_analyst.py tradingagents/agents/analysts/fundamentals_analyst.py tests/agents/test_analyst_prompt_prefixes.py
git commit -m "refactor(prompts): stabilize analyst prompt prefixes"
```

---

## Task 5: Investment Debate Prompt Builders

**Files:**
- Modify: `tradingagents/agents/researchers/bull_researcher.py`
- Modify: `tradingagents/agents/researchers/bear_researcher.py`
- Create: `tests/agents/test_debate_prompt_prefixes.py`

- [ ] **Step 1: Write failing tests for bull and bear prompt builders**

Create `tests/agents/test_debate_prompt_prefixes.py`:

```python
from tradingagents.agents.researchers.bear_researcher import (
    BEAR_RESEARCHER_SYSTEM_PROMPT,
    build_bear_researcher_user_prompt,
)
from tradingagents.agents.researchers.bull_researcher import (
    BULL_RESEARCHER_SYSTEM_PROMPT,
    build_bull_researcher_user_prompt,
)
from tradingagents.agents.utils.prompt_cache import DYNAMIC_CONTEXT_MARKER, prompt_prefix_fingerprint


def _debate_state(ticker: str) -> dict:
    return {
        "company_of_interest": ticker,
        "asset_type": "stock",
        "market_report": f"{ticker} market report",
        "sentiment_report": f"{ticker} sentiment report",
        "news_report": f"{ticker} news report",
        "fundamentals_report": f"{ticker} fundamentals report",
        "derivatives_report": f"{ticker} derivatives report",
        "investment_debate_state": {
            "history": f"{ticker} history",
            "bull_history": "",
            "bear_history": "",
            "current_response": f"{ticker} last response",
            "count": 1,
        },
    }


def test_bull_and_bear_static_prompts_are_run_agnostic():
    for system_prompt in (BULL_RESEARCHER_SYSTEM_PROMPT, BEAR_RESEARCHER_SYSTEM_PROMPT):
        assert "NVDA" not in system_prompt
        assert "AAPL" not in system_prompt
        assert "stock" not in system_prompt.lower()


def test_bull_prefix_ignores_dynamic_state_values():
    messages_a = [
        {"role": "system", "content": BULL_RESEARCHER_SYSTEM_PROMPT},
        {"role": "user", "content": build_bull_researcher_user_prompt(_debate_state("NVDA"))},
    ]
    messages_b = [
        {"role": "system", "content": BULL_RESEARCHER_SYSTEM_PROMPT},
        {"role": "user", "content": build_bull_researcher_user_prompt(_debate_state("AAPL"))},
    ]

    assert prompt_prefix_fingerprint(messages_a) == prompt_prefix_fingerprint(messages_b)
    assert messages_a[1]["content"].startswith(DYNAMIC_CONTEXT_MARKER)
    assert "NVDA market report" in messages_a[1]["content"]


def test_bear_prefix_ignores_dynamic_state_values():
    messages_a = [
        {"role": "system", "content": BEAR_RESEARCHER_SYSTEM_PROMPT},
        {"role": "user", "content": build_bear_researcher_user_prompt(_debate_state("NVDA"))},
    ]
    messages_b = [
        {"role": "system", "content": BEAR_RESEARCHER_SYSTEM_PROMPT},
        {"role": "user", "content": build_bear_researcher_user_prompt(_debate_state("AAPL"))},
    ]

    assert prompt_prefix_fingerprint(messages_a) == prompt_prefix_fingerprint(messages_b)
    assert messages_a[1]["content"].startswith(DYNAMIC_CONTEXT_MARKER)
    assert "NVDA last response" in messages_a[1]["content"]
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/agents/test_debate_prompt_prefixes.py -v`

Expected: FAIL with import errors for `BULL_RESEARCHER_SYSTEM_PROMPT`.

- [ ] **Step 3: Refactor bull researcher**

In `tradingagents/agents/researchers/bull_researcher.py`, add imports:

```python
from tradingagents.agents.utils.agent_utils import build_instrument_context, get_language_instruction
from tradingagents.agents.utils.prompt_cache import budgeted_dynamic_text, stable_join_sections
```

Replace the existing `get_language_instruction` import line with the combined import above.

Add this static prompt:

```python
BULL_RESEARCHER_SYSTEM_PROMPT = """You are a Bull Analyst advocating for investing in the instrument. Your task is to build a strong, evidence-based case emphasizing growth potential, competitive advantages, and positive market indicators. Leverage the provided research and data to address concerns and counter bearish arguments effectively.

Key points to focus on:
- Growth Potential: Highlight market opportunities, revenue or adoption prospects, and scalability.
- Competitive Advantages: Emphasize factors like unique products, strong branding, or dominant market positioning.
- Positive Indicators: Use financial health, industry trends, and recent positive news as evidence.
- Bear Counterpoints: Critically analyze the bear argument with specific data and sound reasoning.
- Engagement: Present your argument conversationally and engage directly with the bear analyst's points.

Use the resources provided in the next message to deliver a compelling bull argument, refute the bear's concerns, and demonstrate the strengths of the bull position."""
```

Add this builder:

```python
def build_bull_researcher_user_prompt(state: dict) -> str:
    debate = state["investment_debate_state"]
    asset_type = state.get("asset_type", "stock")
    return stable_join_sections(
        [
            (
                "Instrument Context",
                build_instrument_context(state["company_of_interest"], asset_type),
            ),
            (
                "Market Research Report",
                budgeted_dynamic_text(
                    state.get("market_report", ""),
                    "prompt_cache_report_budget_chars",
                    5000,
                    "market report",
                ),
            ),
            (
                "Social Media Sentiment Report",
                budgeted_dynamic_text(
                    state.get("sentiment_report", ""),
                    "prompt_cache_report_budget_chars",
                    5000,
                    "sentiment report",
                ),
            ),
            (
                "Latest World Affairs News",
                budgeted_dynamic_text(
                    state.get("news_report", ""),
                    "prompt_cache_report_budget_chars",
                    5000,
                    "news report",
                ),
            ),
            (
                "Fundamentals Report",
                budgeted_dynamic_text(
                    state.get("fundamentals_report", ""),
                    "prompt_cache_report_budget_chars",
                    5000,
                    "fundamentals report",
                ),
            ),
            (
                "Derivatives And Options Report",
                budgeted_dynamic_text(
                    state.get("derivatives_report", ""),
                    "prompt_cache_report_budget_chars",
                    5000,
                    "derivatives report",
                ),
            ),
            (
                "Conversation History Of The Debate",
                budgeted_dynamic_text(
                    debate.get("history", ""),
                    "prompt_cache_debate_budget_chars",
                    8000,
                    "investment debate history",
                ),
            ),
            ("Last Bear Argument", debate.get("current_response", "")),
            (
                "Current Task",
                "Deliver the next bull argument in the investment debate.",
            ),
        ]
    )
```

Inside `bull_node`, remove local report variables that are now read by the builder. Replace the local system and user prompt blocks with:

```python
        system_prompt = apply_fragment(
            BULL_RESEARCHER_SYSTEM_PROMPT + get_language_instruction(),
            persona,
        )
        user_prompt = build_bull_researcher_user_prompt(state)
```

Keep response handling and state updates unchanged.

- [ ] **Step 4: Refactor bear researcher**

In `tradingagents/agents/researchers/bear_researcher.py`, add imports:

```python
from tradingagents.agents.utils.agent_utils import build_instrument_context, get_language_instruction
from tradingagents.agents.utils.prompt_cache import budgeted_dynamic_text, stable_join_sections
```

Add this static prompt:

```python
BEAR_RESEARCHER_SYSTEM_PROMPT = """You are a Bear Analyst making the case against investing in the instrument. Your goal is to present a well-reasoned argument emphasizing risks, challenges, and negative indicators. Leverage the provided research and data to highlight potential downsides and counter bullish arguments effectively.

Key points to focus on:
- Risks and Challenges: Highlight market saturation, financial instability, macroeconomic threats, or other risks that could hinder performance.
- Competitive Weaknesses: Emphasize vulnerabilities such as weaker market positioning, declining innovation, or threats from competitors.
- Negative Indicators: Use evidence from financial data, market trends, or recent adverse news to support your position.
- Bull Counterpoints: Critically analyze the bull argument with specific data and sound reasoning.
- Engagement: Present your argument conversationally and directly engage with the bull analyst's points.

Use the resources provided in the next message to deliver a compelling bear argument, refute the bull's claims, and demonstrate the risks and weaknesses of investing in the instrument."""
```

Add this builder:

```python
def build_bear_researcher_user_prompt(state: dict) -> str:
    debate = state["investment_debate_state"]
    asset_type = state.get("asset_type", "stock")
    return stable_join_sections(
        [
            (
                "Instrument Context",
                build_instrument_context(state["company_of_interest"], asset_type),
            ),
            (
                "Market Research Report",
                budgeted_dynamic_text(
                    state.get("market_report", ""),
                    "prompt_cache_report_budget_chars",
                    5000,
                    "market report",
                ),
            ),
            (
                "Social Media Sentiment Report",
                budgeted_dynamic_text(
                    state.get("sentiment_report", ""),
                    "prompt_cache_report_budget_chars",
                    5000,
                    "sentiment report",
                ),
            ),
            (
                "Latest World Affairs News",
                budgeted_dynamic_text(
                    state.get("news_report", ""),
                    "prompt_cache_report_budget_chars",
                    5000,
                    "news report",
                ),
            ),
            (
                "Fundamentals Report",
                budgeted_dynamic_text(
                    state.get("fundamentals_report", ""),
                    "prompt_cache_report_budget_chars",
                    5000,
                    "fundamentals report",
                ),
            ),
            (
                "Derivatives And Options Report",
                budgeted_dynamic_text(
                    state.get("derivatives_report", ""),
                    "prompt_cache_report_budget_chars",
                    5000,
                    "derivatives report",
                ),
            ),
            (
                "Conversation History Of The Debate",
                budgeted_dynamic_text(
                    debate.get("history", ""),
                    "prompt_cache_debate_budget_chars",
                    8000,
                    "investment debate history",
                ),
            ),
            ("Last Bull Argument", debate.get("current_response", "")),
            (
                "Current Task",
                "Deliver the next bear argument in the investment debate.",
            ),
        ]
    )
```

Inside `bear_node`, replace the local system and user prompt blocks with:

```python
        system_prompt = apply_fragment(
            BEAR_RESEARCHER_SYSTEM_PROMPT + get_language_instruction(),
            persona,
        )
        user_prompt = build_bear_researcher_user_prompt(state)
```

Keep response handling and state updates unchanged.

- [ ] **Step 5: Run debate prompt tests**

Run: `pytest tests/agents/test_debate_prompt_prefixes.py -v`

Expected: PASS, 3 tests.

- [ ] **Step 6: Run graph-related tests**

Run: `pytest tests/test_structured_agents.py tests/test_memory_log.py::TestLegacyRemoval::test_full_pipeline_no_regression -v`

Expected: PASS.

- [ ] **Step 7: Commit investment debate refactor**

```bash
git add tradingagents/agents/researchers/bull_researcher.py tradingagents/agents/researchers/bear_researcher.py tests/agents/test_debate_prompt_prefixes.py
git commit -m "refactor(prompts): stabilize investment debate prompts"
```

---

## Task 6: Risk Debate Prompt Builders

**Files:**
- Modify: `tradingagents/agents/risk_mgmt/aggressive_debator.py`
- Modify: `tradingagents/agents/risk_mgmt/conservative_debator.py`
- Modify: `tradingagents/agents/risk_mgmt/neutral_debator.py`
- Modify: `tests/agents/test_debate_prompt_prefixes.py`

- [ ] **Step 1: Add failing tests for risk debater builders**

Append to `tests/agents/test_debate_prompt_prefixes.py`:

```python
from tradingagents.agents.risk_mgmt.aggressive_debator import (
    AGGRESSIVE_RISK_SYSTEM_PROMPT,
    build_aggressive_risk_user_prompt,
)
from tradingagents.agents.risk_mgmt.conservative_debator import (
    CONSERVATIVE_RISK_SYSTEM_PROMPT,
    build_conservative_risk_user_prompt,
)
from tradingagents.agents.risk_mgmt.neutral_debator import (
    NEUTRAL_RISK_SYSTEM_PROMPT,
    build_neutral_risk_user_prompt,
)


def _risk_state(ticker: str) -> dict:
    return {
        "company_of_interest": ticker,
        "market_report": f"{ticker} market report",
        "sentiment_report": f"{ticker} sentiment report",
        "news_report": f"{ticker} news report",
        "fundamentals_report": f"{ticker} fundamentals report",
        "trader_investment_plan": f"{ticker} trader plan",
        "risk_debate_state": {
            "history": f"{ticker} risk history",
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "current_aggressive_response": f"{ticker} aggressive",
            "current_conservative_response": f"{ticker} conservative",
            "current_neutral_response": f"{ticker} neutral",
            "count": 1,
        },
    }


def test_risk_debater_static_prompts_are_run_agnostic():
    for system_prompt in (
        AGGRESSIVE_RISK_SYSTEM_PROMPT,
        CONSERVATIVE_RISK_SYSTEM_PROMPT,
        NEUTRAL_RISK_SYSTEM_PROMPT,
    ):
        assert "NVDA" not in system_prompt
        assert "AAPL" not in system_prompt
        assert "stock" not in system_prompt.lower()


def test_risk_debater_prefixes_ignore_dynamic_state_values():
    cases = [
        (AGGRESSIVE_RISK_SYSTEM_PROMPT, build_aggressive_risk_user_prompt),
        (CONSERVATIVE_RISK_SYSTEM_PROMPT, build_conservative_risk_user_prompt),
        (NEUTRAL_RISK_SYSTEM_PROMPT, build_neutral_risk_user_prompt),
    ]
    for system_prompt, builder in cases:
        messages_a = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": builder(_risk_state("NVDA"))},
        ]
        messages_b = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": builder(_risk_state("AAPL"))},
        ]
        assert prompt_prefix_fingerprint(messages_a) == prompt_prefix_fingerprint(messages_b)
        assert messages_a[1]["content"].startswith(DYNAMIC_CONTEXT_MARKER)
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/agents/test_debate_prompt_prefixes.py -v`

Expected: FAIL with import errors for `AGGRESSIVE_RISK_SYSTEM_PROMPT`.

- [ ] **Step 3: Add shared risk user-section pattern in each risk debater module**

For each risk debater module, import:

```python
from tradingagents.agents.utils.prompt_cache import budgeted_dynamic_text, stable_join_sections
```

Each module should define a static system prompt constant using the current role instructions with run-specific nouns removed:

```python
AGGRESSIVE_RISK_SYSTEM_PROMPT = """As the Aggressive Risk Analyst, your role is to actively champion high-reward, high-risk opportunities, emphasizing bold strategies and competitive advantages. When evaluating the trader's decision or plan, focus intently on potential upside, growth potential, and innovative benefits, even when these come with elevated risk.

Your task is to create a compelling case for the trader's decision by questioning and critiquing the conservative and neutral stances. Incorporate insights from the sources provided in the next message. If there are no responses from the other viewpoints yet, present your own argument based on the available data.

Engage actively by addressing specific concerns raised, refuting weaknesses in opposing logic, and asserting the benefits of risk-taking to outpace market norms. Output conversationally as if you are speaking without special formatting."""
```

```python
CONSERVATIVE_RISK_SYSTEM_PROMPT = """As the Conservative Risk Analyst, your primary objective is to protect assets, minimize volatility, and ensure steady, reliable growth. You prioritize stability, security, and risk mitigation, carefully assessing potential losses, economic downturns, and market volatility.

Your task is to actively counter the arguments of the aggressive and neutral analysts, highlighting where their views may overlook potential threats or fail to prioritize sustainability. Incorporate insights from the sources provided in the next message. If there are no responses from the other viewpoints yet, present your own argument based on the available data.

Engage by questioning optimism and emphasizing potential downsides that may have been overlooked. Output conversationally as if you are speaking without special formatting."""
```

```python
NEUTRAL_RISK_SYSTEM_PROMPT = """As the Neutral Risk Analyst, your role is to provide a balanced perspective, weighing both the potential benefits and risks of the trader's decision or plan. You prioritize a well-rounded approach, evaluating upsides and downsides while factoring in broader market trends, potential economic shifts, and diversification strategies.

Your task is to challenge both aggressive and conservative analysts, pointing out where each perspective may be overly optimistic or overly cautious. Incorporate insights from the sources provided in the next message. If there are no responses from the other viewpoints yet, present your own argument based on the available data.

Engage actively by analyzing both sides critically and advocating for a moderate risk strategy when warranted. Output conversationally as if you are speaking without special formatting."""
```

- [ ] **Step 4: Add risk user builders**

Add this builder to `aggressive_debator.py`:

```python
def build_aggressive_risk_user_prompt(state: dict) -> str:
    risk = state["risk_debate_state"]
    return stable_join_sections(
        [
            ("Trader Decision", state.get("trader_investment_plan", "")),
            ("Market Research Report", budgeted_dynamic_text(state.get("market_report", ""), "prompt_cache_report_budget_chars", 5000, "market report")),
            ("Social Media Sentiment Report", budgeted_dynamic_text(state.get("sentiment_report", ""), "prompt_cache_report_budget_chars", 5000, "sentiment report")),
            ("Latest World Affairs Report", budgeted_dynamic_text(state.get("news_report", ""), "prompt_cache_report_budget_chars", 5000, "news report")),
            ("Fundamentals Report", budgeted_dynamic_text(state.get("fundamentals_report", ""), "prompt_cache_report_budget_chars", 5000, "fundamentals report")),
            ("Risk Debate History", budgeted_dynamic_text(risk.get("history", ""), "prompt_cache_debate_budget_chars", 8000, "risk debate history")),
            ("Last Conservative Argument", risk.get("current_conservative_response", "")),
            ("Last Neutral Argument", risk.get("current_neutral_response", "")),
            ("Current Task", "Deliver the aggressive risk argument."),
        ]
    )
```

Add this builder to `conservative_debator.py`:

```python
def build_conservative_risk_user_prompt(state: dict) -> str:
    risk = state["risk_debate_state"]
    return stable_join_sections(
        [
            ("Trader Decision", state.get("trader_investment_plan", "")),
            ("Market Research Report", budgeted_dynamic_text(state.get("market_report", ""), "prompt_cache_report_budget_chars", 5000, "market report")),
            ("Social Media Sentiment Report", budgeted_dynamic_text(state.get("sentiment_report", ""), "prompt_cache_report_budget_chars", 5000, "sentiment report")),
            ("Latest World Affairs Report", budgeted_dynamic_text(state.get("news_report", ""), "prompt_cache_report_budget_chars", 5000, "news report")),
            ("Fundamentals Report", budgeted_dynamic_text(state.get("fundamentals_report", ""), "prompt_cache_report_budget_chars", 5000, "fundamentals report")),
            ("Risk Debate History", budgeted_dynamic_text(risk.get("history", ""), "prompt_cache_debate_budget_chars", 8000, "risk debate history")),
            ("Last Aggressive Argument", risk.get("current_aggressive_response", "")),
            ("Last Neutral Argument", risk.get("current_neutral_response", "")),
            ("Current Task", "Deliver the conservative risk argument."),
        ]
    )
```

Add this builder to `neutral_debator.py`:

```python
def build_neutral_risk_user_prompt(state: dict) -> str:
    risk = state["risk_debate_state"]
    return stable_join_sections(
        [
            ("Trader Decision", state.get("trader_investment_plan", "")),
            ("Market Research Report", budgeted_dynamic_text(state.get("market_report", ""), "prompt_cache_report_budget_chars", 5000, "market report")),
            ("Social Media Sentiment Report", budgeted_dynamic_text(state.get("sentiment_report", ""), "prompt_cache_report_budget_chars", 5000, "sentiment report")),
            ("Latest World Affairs Report", budgeted_dynamic_text(state.get("news_report", ""), "prompt_cache_report_budget_chars", 5000, "news report")),
            ("Fundamentals Report", budgeted_dynamic_text(state.get("fundamentals_report", ""), "prompt_cache_report_budget_chars", 5000, "fundamentals report")),
            ("Risk Debate History", budgeted_dynamic_text(risk.get("history", ""), "prompt_cache_debate_budget_chars", 8000, "risk debate history")),
            ("Last Aggressive Argument", risk.get("current_aggressive_response", "")),
            ("Last Conservative Argument", risk.get("current_conservative_response", "")),
            ("Current Task", "Deliver the neutral risk argument."),
        ]
    )
```

Inside each node function, replace the local system/user prompt blocks with the matching constant and builder:

```python
        system_prompt = apply_fragment(
            AGGRESSIVE_RISK_SYSTEM_PROMPT + get_language_instruction(),
            persona,
        )
        user_prompt = build_aggressive_risk_user_prompt(state)
```

Use `CONSERVATIVE_RISK_SYSTEM_PROMPT` plus `build_conservative_risk_user_prompt(state)` in the conservative module, and `NEUTRAL_RISK_SYSTEM_PROMPT` plus `build_neutral_risk_user_prompt(state)` in the neutral module. Keep response handling and state updates unchanged.

- [ ] **Step 5: Run risk prompt tests**

Run: `pytest tests/agents/test_debate_prompt_prefixes.py -v`

Expected: PASS.

- [ ] **Step 6: Run risk graph and memory tests**

Run: `pytest tests/test_memory_log.py::TestPortfolioManagerInjection tests/test_structured_agents.py -v`

Expected: PASS.

- [ ] **Step 7: Commit risk debate refactor**

```bash
git add tradingagents/agents/risk_mgmt/aggressive_debator.py tradingagents/agents/risk_mgmt/conservative_debator.py tradingagents/agents/risk_mgmt/neutral_debator.py tests/agents/test_debate_prompt_prefixes.py
git commit -m "refactor(prompts): stabilize risk debate prompts"
```

---

## Task 7: Structured Synthesis Prompt Builders

**Files:**
- Modify: `tradingagents/agents/managers/research_manager.py`
- Modify: `tradingagents/agents/trader/trader.py`
- Modify: `tradingagents/agents/managers/portfolio_manager.py`
- Modify: `tests/test_structured_agents.py`
- Modify: `tests/test_memory_log.py`

- [ ] **Step 1: Add failing structured-agent prefix tests**

Append to `tests/test_structured_agents.py`:

```python
from tradingagents.agents.managers.research_manager import (
    RESEARCH_MANAGER_SYSTEM_PROMPT,
    build_research_manager_user_prompt,
)
from tradingagents.agents.trader.trader import (
    TRADER_SYSTEM_PROMPT,
    build_trader_user_prompt,
)
from tradingagents.agents.utils.prompt_cache import DYNAMIC_CONTEXT_MARKER, prompt_prefix_fingerprint


def test_research_manager_prefix_ignores_ticker_and_debate_history():
    state_a = _make_rm_state()
    state_a["company_of_interest"] = "NVDA"
    state_b = _make_rm_state()
    state_b["company_of_interest"] = "AAPL"
    state_b["investment_debate_state"]["history"] = "Different debate"

    messages_a = [
        {"role": "system", "content": RESEARCH_MANAGER_SYSTEM_PROMPT},
        {"role": "user", "content": build_research_manager_user_prompt(state_a)},
    ]
    messages_b = [
        {"role": "system", "content": RESEARCH_MANAGER_SYSTEM_PROMPT},
        {"role": "user", "content": build_research_manager_user_prompt(state_b)},
    ]

    assert prompt_prefix_fingerprint(messages_a) == prompt_prefix_fingerprint(messages_b)
    assert messages_a[1]["content"].startswith(DYNAMIC_CONTEXT_MARKER)


def test_trader_prefix_ignores_ticker_and_investment_plan():
    state_a = _make_trader_state()
    state_a["company_of_interest"] = "NVDA"
    state_b = _make_trader_state()
    state_b["company_of_interest"] = "AAPL"
    state_b["investment_plan"] = "Different plan"

    messages_a = [
        {"role": "system", "content": TRADER_SYSTEM_PROMPT},
        {"role": "user", "content": build_trader_user_prompt(state_a)},
    ]
    messages_b = [
        {"role": "system", "content": TRADER_SYSTEM_PROMPT},
        {"role": "user", "content": build_trader_user_prompt(state_b)},
    ]

    assert prompt_prefix_fingerprint(messages_a) == prompt_prefix_fingerprint(messages_b)
    assert messages_a[1]["content"].startswith(DYNAMIC_CONTEXT_MARKER)
```

Append to `tests/test_memory_log.py` near `TestPortfolioManagerInjection`:

```python
from tradingagents.agents.managers.portfolio_manager import (
    PORTFOLIO_MANAGER_SYSTEM_PROMPT,
    build_portfolio_manager_user_prompt,
)
from tradingagents.agents.utils.prompt_cache import (
    DYNAMIC_CONTEXT_MARKER,
    prompt_prefix_fingerprint,
)


def test_portfolio_manager_prefix_ignores_dynamic_state_values():
    state_a = _make_pm_state(past_context="NVDA lesson")
    state_a["company_of_interest"] = "NVDA"
    state_b = _make_pm_state(past_context="AAPL lesson")
    state_b["company_of_interest"] = "AAPL"
    state_b["investment_plan"] = "Different research plan"

    messages_a = [
        {"role": "system", "content": PORTFOLIO_MANAGER_SYSTEM_PROMPT},
        {"role": "user", "content": build_portfolio_manager_user_prompt(state_a)},
    ]
    messages_b = [
        {"role": "system", "content": PORTFOLIO_MANAGER_SYSTEM_PROMPT},
        {"role": "user", "content": build_portfolio_manager_user_prompt(state_b)},
    ]

    assert prompt_prefix_fingerprint(messages_a) == prompt_prefix_fingerprint(messages_b)
    assert messages_a[1]["content"].startswith(DYNAMIC_CONTEXT_MARKER)
```

- [ ] **Step 2: Run structured prompt tests to verify failure**

Run: `pytest tests/test_structured_agents.py tests/test_memory_log.py::test_portfolio_manager_prefix_ignores_dynamic_state_values -v`

Expected: FAIL with import errors for `RESEARCH_MANAGER_SYSTEM_PROMPT` or `PORTFOLIO_MANAGER_SYSTEM_PROMPT`.

- [ ] **Step 3: Refactor research manager**

In `tradingagents/agents/managers/research_manager.py`, import:

```python
from tradingagents.agents.utils.prompt_cache import budgeted_dynamic_text, stable_join_sections
```

Add:

```python
RESEARCH_MANAGER_SYSTEM_PROMPT = """As the Research Manager and debate facilitator, your role is to critically evaluate this round of debate and deliver a clear, actionable investment plan for the trader.

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction in the bull thesis; recommend taking or growing the position
- **Overweight**: Constructive view; recommend gradually increasing exposure
- **Hold**: Balanced view; recommend maintaining the current position
- **Underweight**: Cautious view; recommend trimming exposure
- **Sell**: Strong conviction in the bear thesis; recommend exiting or avoiding the position

Commit to a clear stance whenever the debate's strongest arguments warrant one; reserve Hold for situations where the evidence on both sides is genuinely balanced."""


def build_research_manager_user_prompt(state: dict) -> str:
    history = state["investment_debate_state"].get("history", "")
    prior_pack = state.get("prior_analysis_pack_context", "")
    return stable_join_sections(
        [
            ("Instrument Context", build_instrument_context(state["company_of_interest"])),
            (
                "Debate History",
                budgeted_dynamic_text(
                    history,
                    "prompt_cache_debate_budget_chars",
                    8000,
                    "investment debate history",
                ),
            ),
            (
                "Reusable Prior Analysis Pack",
                budgeted_dynamic_text(
                    prior_pack,
                    "prompt_cache_prior_pack_budget_chars",
                    8000,
                    "prior analysis pack",
                ),
            ),
            ("Current Task", "Produce the structured investment plan."),
        ]
    )
```

Inside `research_manager_node`, replace local `system_prompt` and `user_prompt` with:

```python
        system_prompt = apply_fragment(
            RESEARCH_MANAGER_SYSTEM_PROMPT + get_language_instruction(),
            persona,
        )
        user_prompt = build_research_manager_user_prompt(state)
```

Keep `invoke_structured_or_freetext` unchanged.

- [ ] **Step 4: Refactor trader**

In `tradingagents/agents/trader/trader.py`, import:

```python
from tradingagents.agents.utils.prompt_cache import budgeted_dynamic_text, stable_join_sections
```

Add:

```python
TRADER_SYSTEM_PROMPT = (
    "You are a trading agent analyzing market data to make investment decisions. "
    "Based on your analysis, provide a specific recommendation to buy, sell, or hold. "
    "Anchor your reasoning in the analysts' reports and the research plan."
)


def build_trader_user_prompt(state: dict) -> str:
    company_name = state["company_of_interest"]
    asset_type = state.get("asset_type", "stock")
    return stable_join_sections(
        [
            ("Instrument Context", build_instrument_context(company_name, asset_type)),
            (
                "Research Manager Investment Plan",
                budgeted_dynamic_text(
                    state.get("investment_plan", ""),
                    "prompt_cache_report_budget_chars",
                    5000,
                    "research manager investment plan",
                ),
            ),
            (
                "Reusable Prior Analysis Pack",
                budgeted_dynamic_text(
                    state.get("prior_analysis_pack_context", ""),
                    "prompt_cache_prior_pack_budget_chars",
                    8000,
                    "prior analysis pack",
                ),
            ),
            ("Current Task", "Produce the transaction proposal."),
        ]
    )
```

Inside `trader_node`, replace the system prompt block and user content block with:

```python
        system_prompt = apply_fragment(
            TRADER_SYSTEM_PROMPT + get_language_instruction(),
            persona,
        )
        user_prompt = build_trader_user_prompt(state)
```

Use `{"role": "user", "content": user_prompt}` in `messages`.

- [ ] **Step 5: Refactor portfolio manager**

In `tradingagents/agents/managers/portfolio_manager.py`, import:

```python
from tradingagents.agents.utils.prompt_cache import budgeted_dynamic_text, stable_join_sections
```

Add:

```python
PORTFOLIO_MANAGER_SYSTEM_PROMPT = """As the Portfolio Manager, synthesize the risk analysts' debate and deliver the final trading decision.

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction to enter or add to position
- **Overweight**: Favorable outlook, gradually increase exposure
- **Hold**: Maintain current position, no action needed
- **Underweight**: Reduce exposure, take partial profits
- **Sell**: Exit position or avoid entry

Be decisive and ground every conclusion in specific evidence from the analysts."""


def build_portfolio_manager_user_prompt(state: dict, persona=None) -> str:
    risk_debate_state = state["risk_debate_state"]
    history = format_weighted_risk_debate(risk_debate_state, persona)
    return stable_join_sections(
        [
            ("Instrument Context", build_instrument_context(state["company_of_interest"])),
            (
                "Research Manager Investment Plan",
                budgeted_dynamic_text(
                    state.get("investment_plan", ""),
                    "prompt_cache_report_budget_chars",
                    5000,
                    "research manager investment plan",
                ),
            ),
            (
                "Trader Transaction Proposal",
                budgeted_dynamic_text(
                    state.get("trader_investment_plan", ""),
                    "prompt_cache_report_budget_chars",
                    5000,
                    "trader transaction proposal",
                ),
            ),
            (
                "Lessons From Prior Decisions And Outcomes",
                budgeted_dynamic_text(
                    state.get("past_context", ""),
                    "prompt_cache_memory_budget_chars",
                    6000,
                    "memory lessons",
                ),
            ),
            (
                "Reusable Prior Analysis Pack",
                budgeted_dynamic_text(
                    state.get("prior_analysis_pack_context", ""),
                    "prompt_cache_prior_pack_budget_chars",
                    8000,
                    "prior analysis pack",
                ),
            ),
            (
                "Risk Analysts Debate History",
                budgeted_dynamic_text(
                    history,
                    "prompt_cache_debate_budget_chars",
                    8000,
                    "risk debate history",
                ),
            ),
            ("Current Task", "Produce the final portfolio decision."),
        ]
    )
```

Inside `portfolio_manager_node`, call:

```python
        system_prompt = apply_fragment(
            PORTFOLIO_MANAGER_SYSTEM_PROMPT + get_language_instruction(),
            persona,
        )
        user_prompt = build_portfolio_manager_user_prompt(state, persona=persona)
```

Use `{"role": "user", "content": user_prompt}` in `messages`.

- [ ] **Step 6: Update memory-log assertion for marker placement**

In `tests/test_memory_log.py::TestPortfolioManagerInjection::test_pm_prompt_includes_past_context`, keep the existing assertions and add:

```python
        assert "## Dynamic Run Context" in prompt_text
```

In `test_pm_no_past_context_no_section`, update the omitted-section assertion to:

```python
        assert "Lessons From Prior Decisions And Outcomes" not in prompt_text
```

- [ ] **Step 7: Run structured and memory tests**

Run: `pytest tests/test_structured_agents.py tests/test_memory_log.py -v`

Expected: PASS.

- [ ] **Step 8: Commit structured synthesis refactor**

```bash
git add tradingagents/agents/managers/research_manager.py tradingagents/agents/trader/trader.py tradingagents/agents/managers/portfolio_manager.py tests/test_structured_agents.py tests/test_memory_log.py
git commit -m "refactor(prompts): stabilize synthesis prompts"
```

---

## Task 8: Cache Ratio Reporting

**Files:**
- Modify: `tradingagents/dashboard/panels/costs.py`
- Modify: `tests/dashboard/test_costs_panel.py`

- [ ] **Step 1: Write failing dashboard aggregation test**

Append to `tests/dashboard/test_costs_panel.py`:

```python

def test_fetch_daily_cost_trend_includes_cache_ratio(tmp_path):
    from tradingagents.dashboard.panels.costs import fetch_daily_cost_trend

    conn = iic_connect(str(tmp_path / "iic.db"))
    store.insert_run(
        conn,
        run_id="r-cache",
        ticker="AAPL",
        persona_id="macro",
        started_ts="2026-05-25T10:00:00+00:00",
        artifact_dir="runs/r-cache",
    )
    store.finalize_run(
        conn,
        run_id="r-cache",
        ended_ts="2026-05-25T10:05:00+00:00",
        status="complete",
        decision="BUY",
        confidence=0.7,
    )
    store.record_cost(
        conn,
        run_id="r-cache",
        provider="deepseek",
        model="deepseek-v4-flash",
        in_tokens=1000,
        out_tokens=100,
        usd_estimate=0.001,
        cache_hit_tokens=750,
        cache_miss_tokens=250,
    )

    rows = fetch_daily_cost_trend(conn, days=3650)
    row = next(r for r in rows if r["model"] == "deepseek-v4-flash")

    assert row["cache_hit_tokens"] == 750
    assert row["cache_miss_tokens"] == 250
    assert row["cache_hit_ratio"] == pytest.approx(0.75)
```

- [ ] **Step 2: Run dashboard test to verify failure**

Run: `pytest tests/dashboard/test_costs_panel.py -v`

Expected: FAIL with `KeyError: 'cache_hit_tokens'`.

- [ ] **Step 3: Update cost aggregation query**

Modify `tradingagents/dashboard/panels/costs.py`:

```python
"""Costs panel — daily cost / token trend chart."""

from __future__ import annotations

import sqlite3


def fetch_daily_cost_trend(conn: sqlite3.Connection, *, days: int = 30) -> list[dict]:
    rows = conn.execute(
        """
        SELECT substr(r.started_ts, 1, 10) AS day,
               c.model AS model,
               SUM(c.usd_estimate) AS total_usd,
               SUM(c.in_tokens) AS in_tokens,
               SUM(c.out_tokens) AS out_tokens,
               SUM(COALESCE(c.cache_hit_tokens, 0)) AS cache_hit_tokens,
               SUM(COALESCE(c.cache_miss_tokens, 0)) AS cache_miss_tokens
        FROM costs c
        JOIN runs r ON r.run_id = c.run_id
        WHERE datetime(r.started_ts) > datetime('now', ?)
        GROUP BY day, c.model
        ORDER BY day ASC, c.model ASC
        """,
        (f"-{int(days)} days",),
    ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        hit = int(item.get("cache_hit_tokens") or 0)
        miss = int(item.get("cache_miss_tokens") or 0)
        total = hit + miss
        item["cache_hit_ratio"] = (hit / total) if total > 0 else None
        out.append(item)
    return out
```

- [ ] **Step 4: Run dashboard tests**

Run: `pytest tests/dashboard/test_costs_panel.py -v`

Expected: PASS.

- [ ] **Step 5: Run cache instrumentation tests**

Run: `pytest tests/graph/test_cache_token_capture.py tests/graph/test_cache_ratio_metrics.py -v`

Expected: PASS.

- [ ] **Step 6: Commit reporting change**

```bash
git add tradingagents/dashboard/panels/costs.py tests/dashboard/test_costs_panel.py
git commit -m "feat(costs): report DeepSeek cache hit ratio"
```

---

## Task 9: DeepSeek Prompt Cache Warm-Up Script

**Files:**
- Create: `scripts/warm_deepseek_prompt_cache.py`
- Create: `tests/scripts/test_warm_deepseek_prompt_cache.py`

- [ ] **Step 1: Write failing warm-up tests**

Create `tests/scripts/test_warm_deepseek_prompt_cache.py`:

```python
from scripts.warm_deepseek_prompt_cache import build_warmup_messages, iter_warmup_families


def test_iter_warmup_families_has_core_investment_team_prompts():
    names = [family.name for family in iter_warmup_families()]

    assert "market" in names
    assert "sentiment" in names
    assert "research_manager" in names
    assert "portfolio_manager" in names


def test_build_warmup_messages_use_static_prefix_and_tiny_tail():
    family = next(f for f in iter_warmup_families() if f.name == "sentiment")

    messages = build_warmup_messages(family)

    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "CACHE-WARMUP" in messages[1]["content"]
    assert "2000-01-01" in messages[1]["content"]
    assert "## Dynamic Run Context" in messages[1]["content"]
```

- [ ] **Step 2: Run warm-up tests to verify failure**

Run: `pytest tests/scripts/test_warm_deepseek_prompt_cache.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.warm_deepseek_prompt_cache'`.

- [ ] **Step 3: Implement warm-up script**

Create `scripts/warm_deepseek_prompt_cache.py`:

```python
"""Warm DeepSeek official API context cache for TradingAgents prompt prefixes."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Callable, Iterable

from tradingagents.agents.analysts.derivative_analyst import (
    DERIVATIVES_SYSTEM_MESSAGE,
    build_derivatives_user_prompt,
)
from tradingagents.agents.analysts.market_analyst import (
    MARKET_SYSTEM_MESSAGE,
    build_market_user_prompt,
)
from tradingagents.agents.analysts.sentiment_analyst import (
    SENTIMENT_SYSTEM_MESSAGE,
    build_sentiment_user_prompt,
)
from tradingagents.agents.managers.portfolio_manager import (
    PORTFOLIO_MANAGER_SYSTEM_PROMPT,
    build_portfolio_manager_user_prompt,
)
from tradingagents.agents.managers.research_manager import (
    RESEARCH_MANAGER_SYSTEM_PROMPT,
    build_research_manager_user_prompt,
)
from tradingagents.agents.trader.trader import TRADER_SYSTEM_PROMPT, build_trader_user_prompt
from tradingagents.agents.utils.agent_utils import build_instrument_context
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.cost_callback import RunCostCallback
from tradingagents.graph.run_recorder import compute_cache_hit_ratio
from tradingagents.llm_clients import create_llm_client


@dataclass(frozen=True)
class WarmupFamily:
    name: str
    tier: str
    system_message: str
    user_builder: Callable[[], str]


def _warmup_state() -> dict:
    return {
        "company_of_interest": "CACHE-WARMUP",
        "asset_type": "stock",
        "trade_date": "2000-01-01",
        "market_report": "No market report. Cache warm-up only.",
        "sentiment_report": "No sentiment report. Cache warm-up only.",
        "news_report": "No news report. Cache warm-up only.",
        "fundamentals_report": "No fundamentals report. Cache warm-up only.",
        "derivatives_report": "No derivatives report. Cache warm-up only.",
        "investment_plan": "Hold. Cache warm-up only.",
        "trader_investment_plan": "Hold. Cache warm-up only.",
        "past_context": "",
        "prior_analysis_pack_context": "",
        "investment_debate_state": {
            "history": "Cache warm-up investment debate.",
            "bull_history": "",
            "bear_history": "",
            "current_response": "",
            "count": 0,
        },
        "risk_debate_state": {
            "history": "Cache warm-up risk debate.",
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
            "count": 0,
        },
    }


def iter_warmup_families() -> Iterable[WarmupFamily]:
    instrument_context = build_instrument_context("CACHE-WARMUP")
    state = _warmup_state()
    yield WarmupFamily(
        "market",
        "quick",
        MARKET_SYSTEM_MESSAGE,
        lambda: build_market_user_prompt(
            current_date="2000-01-01",
            instrument_context=instrument_context,
            market_snapshot_context="No snapshot. Cache warm-up only.",
        ),
    )
    yield WarmupFamily(
        "sentiment",
        "quick",
        SENTIMENT_SYSTEM_MESSAGE,
        lambda: build_sentiment_user_prompt(
            ticker="CACHE-WARMUP",
            instrument_context=instrument_context,
            start_date="1999-12-25",
            end_date="2000-01-01",
            news_block="No news. Cache warm-up only.",
            stocktwits_block="No StockTwits. Cache warm-up only.",
            reddit_block="No Reddit. Cache warm-up only.",
        ),
    )
    yield WarmupFamily(
        "derivatives",
        "quick",
        DERIVATIVES_SYSTEM_MESSAGE,
        lambda: build_derivatives_user_prompt(
            current_date="2000-01-01",
            instrument_context=instrument_context,
        ),
    )
    yield WarmupFamily(
        "research_manager",
        "deep",
        RESEARCH_MANAGER_SYSTEM_PROMPT,
        lambda: build_research_manager_user_prompt(state),
    )
    yield WarmupFamily(
        "trader",
        "quick",
        TRADER_SYSTEM_PROMPT,
        lambda: build_trader_user_prompt(state),
    )
    yield WarmupFamily(
        "portfolio_manager",
        "deep",
        PORTFOLIO_MANAGER_SYSTEM_PROMPT,
        lambda: build_portfolio_manager_user_prompt(state),
    )


def build_warmup_messages(family: WarmupFamily) -> list[dict]:
    return [
        {"role": "system", "content": family.system_message},
        {"role": "user", "content": family.user_builder()},
    ]


def _model_for_tier(config: dict, tier: str) -> str:
    return config["deep_think_llm"] if tier == "deep" else config["quick_think_llm"]


def run_warmup(*, dry_run: bool = False, config: dict | None = None) -> None:
    cfg = dict(DEFAULT_CONFIG)
    if config:
        cfg.update(config)
    if cfg.get("llm_provider") != "deepseek":
        raise RuntimeError("warm-up supports DeepSeek official API runs only")

    for family in iter_warmup_families():
        model = _model_for_tier(cfg, family.tier)
        messages = build_warmup_messages(family)
        if dry_run:
            print(f"{family.name}: model={model} messages={len(messages)}")
            continue

        callback = RunCostCallback()
        client = create_llm_client(
            provider="deepseek",
            model=model,
            base_url=cfg.get("backend_url"),
            callbacks=[callback],
        )
        llm = client.get_llm()
        llm.invoke(messages)
        totals = callback.totals_by_model()
        counts = next(iter(totals.values()), {})
        hit = counts.get("cache_hit_tokens", 0)
        miss = counts.get("cache_miss_tokens", 0)
        ratio = compute_cache_hit_ratio(hit, miss)
        print(
            f"{family.name}: model={model} "
            f"in_tokens={counts.get('in_tokens', 0)} "
            f"cache_hit_tokens={hit} cache_miss_tokens={miss} "
            f"cache_hit_ratio={ratio}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run_warmup(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run warm-up tests**

Run: `pytest tests/scripts/test_warm_deepseek_prompt_cache.py -v`

Expected: PASS.

- [ ] **Step 5: Run dry-run manually**

Run: `python scripts/warm_deepseek_prompt_cache.py --dry-run`

Expected: output includes `market: model=deepseek-v4-flash` and `portfolio_manager: model=deepseek-v4-pro`.

- [ ] **Step 6: Commit warm-up script**

```bash
git add scripts/warm_deepseek_prompt_cache.py tests/scripts/test_warm_deepseek_prompt_cache.py
git commit -m "feat(deepseek): add prompt cache warm-up script"
```

---

## Task 10: Final Verification

**Files:**
- No new files.

- [ ] **Step 1: Run focused prompt and cache tests**

Run:

```bash
pytest \
  tests/agents/test_prompt_cache_utils.py \
  tests/test_prompt_cache_config.py \
  tests/agents/test_analyst_prompt_prefixes.py \
  tests/agents/test_debate_prompt_prefixes.py \
  tests/test_structured_agents.py \
  tests/test_memory_log.py \
  tests/dashboard/test_costs_panel.py \
  tests/graph/test_cache_token_capture.py \
  tests/graph/test_cache_ratio_metrics.py \
  tests/scripts/test_warm_deepseek_prompt_cache.py \
  -v
```

Expected: PASS.

- [ ] **Step 2: Run broader non-network suite**

Run:

```bash
pytest tests -m "not integration" -v
```

Expected: PASS. If the suite exposes an unrelated pre-existing failure, capture the exact failing test names and error summaries before deciding whether to fix or defer.

- [ ] **Step 3: Verify no gateway-only cache parameters were added**

Run:

```bash
rg -n "prompt_cache_key|X-Session-ID|x-session-id|sticky routing|gateway routing" tradingagents scripts tests
```

Expected: no matches.

- [ ] **Step 4: Verify working tree contains only intended changes**

Run:

```bash
git status --short
```

Expected: no tracked modifications. Existing unrelated untracked files may remain; do not add them.

- [ ] **Step 5: Final commit if verification-only fixes were needed**

If Step 1 or Step 2 required a small compatibility fix, commit only the files touched for that fix:

```bash
git add <files from the compatibility fix>
git commit -m "test: stabilize DeepSeek cache prompt coverage"
```

Expected: commit succeeds.
