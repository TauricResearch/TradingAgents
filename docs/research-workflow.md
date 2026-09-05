# Research Workflow MVP

`research_workflow.py` is the first local end-to-end ticker flow:

```python
from tradingagents.research_platform.research_workflow import (
    ResearchWorkflowConfig,
    run_ticker_research,
)
```

The workflow:

1. Resolves a basic `InstrumentIdentity`.
2. Fetches prices, fundamentals, and news from a `DataProvider`.
3. Optionally saves normalized artifacts to an `ArtifactStore`.
4. Builds lightweight deterministic `AnalystNote` records from the data.
5. Builds a neutral deterministic `InvestmentThesis` when notes exist.
6. Optionally reviews a supplied `TradeSignal` with deterministic risk rules.
7. Optionally backtests the risk-approved signal.
8. Renders and optionally writes a Markdown research report.

## Why The Workflow Accepts A Signal

This MVP does not ask an LLM to invent a trade. It accepts an already validated
`TradeSignal`, which can later come from:

- a structured LLM agent
- a rule-based screen
- a manually entered thesis
- a legacy Portfolio Manager markdown bridge

That keeps the pipeline honest: data collection, risk review, backtesting, and
reporting can be tested without live model calls.

## Next Step

The next slice should add a small CLI command around this workflow, for example:

```text
python -m tradingagents.research_platform.cli_report NVDA --as-of 2026-01-05
```

The command can start with fixture/manual signal support before adding live
provider credentials.
