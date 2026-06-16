---
type: architecture
tags:
  - opencloude-agent
  - scoring
---

# Opportunity Scoring

[[OpportunityScanner]] wybiera najbardziej interesujące tickery z market snapshotu.

## Domyślne ustawienie

- `max_candidates = 3`

## Formula score

Bazowy score to `50.0`.

Do niego dodawane są:

```text
relative_strength * 100.0
momentum_20d * 50.0
volume bonus capped at 5.0
```

W praktyce:

```text
score = 50.0 + relative_strength * 100.0 + momentum_20d * 50.0 + min(volume_bonus, 5.0)
```

## Wynik

Każda okazja jest reprezentowana przez [[Opportunity]]:

```python
Opportunity(
    ticker=...,
    score=...,
    reason=...,
    snapshot=...
)
```

## Linki

- [[OpportunityScanner]]
- [[Opportunity]]
- [[Agent Loop]]
- [[Risk Evaluation]]
