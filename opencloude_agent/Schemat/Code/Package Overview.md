---
type: code
tags:
  - opencloude-agent
  - python
  - package
---

# Package Overview

Pakiet `opencloude_agent` eksportuje główne komponenty agenta z pliku [[run.py]].

## Eksporty

```python
DEFAULT_WATCHLIST
MarketWatcher
OpenClaudeContinuousAgent
Opportunity
OpportunityScanner
PaperPortfolio
ReportWriter
RiskGuard
```

## Odpowiedzialność pakietu

Pakiet udostępnia agenta paper-tradingowego, który może działać:

- jednorazowo: `python -m opencloude_agent.run`,
- w pętli: `python -m opencloude_agent.run --watch`.

## Linki

- [[run.py]]
- [[Agent Loop]]
- [[CLI Entry Points]]
