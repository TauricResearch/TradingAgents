---
type: tests
tags:
  - opencloude-agent
  - tests
  - unittest
---

# test_opencloude_agent

Plik `tests/test_opencloude_agent.py` zawiera testy jednostkowe oparte na `unittest`.

## Testowane obszary

### `PaperPortfolio`

- Portfel startuje z `10_000.0 USD`.
- `to_dict()` zwraca początkową wartość portfela.
- `simulate_buy()` zmniejsza gotówkę i zwiększa pozycję.
- `simulate_sell()` zwiększa gotówkę i zmniejsza pozycję.

### `OpportunityScanner`

- Ogranicza liczbę kandydatów zgodnie z `max_candidates`.
- Sortuje okazje po wyniku.
- W przykładzie testowym `AAPL` wygrywa z `MSFT`.

### `RiskGuard`

- Brak okazji oznacza poziom `watch`.
- Ostrzeżenie zawiera tekst `No opportunities selected`.

### `ReportWriter`

- Tworzy `watch_log.jsonl`.
- Tworzy `daily_summary.md`.
- Zapisuje poprawny JSON w JSONL.
- Dopisuje tekstowy log do `log.txt`.

### `MarketWatcher`

- Pusty DataFrame jest normalizowany do pustego snapshotu `{}`.

## Linki

- [[Paper Portfolio]]
- [[Opportunity Scoring]]
- [[Risk Evaluation]]
- [[Reporting and Persistence]]
- [[Market Data Flow]]
