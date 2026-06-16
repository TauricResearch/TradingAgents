---
type: code
tags:
  - opencloude-agent
  - python
  - package-init
---

# __init__.py

Plik `__init__.py` definiuje publiczny eksport pakietu `opencloude_agent`.

## Eksporty

```python
from .run import (
    DEFAULT_WATCHLIST,
    MarketWatcher,
    OpenClaudeContinuousAgent,
    Opportunity,
    OpportunityScanner,
    PaperPortfolio,
    ReportWriter,
    RiskGuard,
)
```

## `__all__`

```python
__all__ = [
    "DEFAULT_WATCHLIST",
    "MarketWatcher",
    "OpenClaudeContinuousAgent",
    "Opportunity",
    "OpportunityScanner",
    "PaperPortfolio",
    "ReportWriter",
    "RiskGuard",
]
```

## Linki

- [[run.py]]
- [[Package Overview]]
