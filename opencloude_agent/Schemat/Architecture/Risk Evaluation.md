---
type: architecture
tags:
  - opencloude-agent
  - risk
---

# Risk Evaluation

[[RiskGuard]] ocenia, czy cykl może kontynuować normalne raportowanie.

## Poziomy ryzyka

- `safe` — brak istotnych ostrzeżeń.
- `watch` — wymagana ostrożność, np. brak okazji.
- `blocked_by_risk` — portfel jest zbyt skoncentrowany.

## Obsługiwane przypadki

- Brak okazji w cyklu.
- Wysoka koncentracja pozycji w portfelu.
- Brak dostępnych bezpiecznych decyzji.

## Dane wejściowe

- Stan [[Paper Portfolio]].
- Lista [[Opportunity]].

## Linki

- [[RiskGuard]]
- [[Paper Portfolio]]
- [[Opportunity Scoring]]
- [[Agent Loop]]
