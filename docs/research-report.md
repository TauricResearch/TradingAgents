# Research Report MVP

`research_report.py` renders a personal ticker report from validated platform
artifacts:

```python
from tradingagents.research_platform.research_report import (
    ResearchReportBundle,
    render_research_report,
    write_research_report,
)
```

The report bundle can include:

- normalized `PriceBar` records
- `FundamentalSnapshot` records
- `NewsItem` records
- structured `AnalystNote` records
- an `InvestmentThesis`
- a validated `TradeSignal`
- a deterministic `RiskReview`
- a `BacktestResult`

## Report Sections

The Markdown report currently renders:

1. Market snapshot
2. Fundamentals
3. News
4. Analyst notes
5. Investment thesis
6. Trade signal
7. Risk review
8. Backtest
9. Provenance

## Design Rule

The report is generated from typed artifacts, not raw LLM output. LLM-written
sections can appear as `AnalystNote`, `InvestmentThesis`, or `TradeSignal`
rationale, but numerical metrics, risk decisions, and data provenance come from
deterministic code paths.
