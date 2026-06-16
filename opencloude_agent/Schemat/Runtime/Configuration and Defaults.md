---
type: runtime
tags:
  - opencloude-agent
  - defaults
---

# Configuration and Defaults

## Domyślne wartości

```python
DEFAULT_WATCHLIST = ["AAPL", "MSFT", "NVDA", "TSLA", "SPY"]
max_candidates = 3
results_dir = "results"
watch = False
interval_seconds = 3600
```

## Parametry CLI

- `--watchlist` — lista tickerów oddzielona przecinkami.
- `--max-candidates` — liczba kandydatów do wyboru.
- `--results-dir` — katalog wyników.
- `--watch` — uruchamia ciągłą pętlę.
- `--interval-seconds` — odstęp między cyklami w pętli.

## Stan papierowego portfela

- Początkowa gotówka: `10 000 USD`.
- Pozycje początkowe: brak.
- Alokacja na zakup: `max(cash_usd * 0.10, 1000.0)`.

## Linki

- [[CLI Entry Points]]
- [[Paper Portfolio]]
- [[Opportunity Scoring]]
