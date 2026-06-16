---
type: result
tags:
  - opencloude-agent
  - watch-log
---

# Watch Log

Źródłowy plik: `results/continuous/watch_log.jsonl`.

## Format

Każda linia JSON zawiera:

```json
{
  "timestamp": "...",
  "snapshot": {
    "AAPL": {
      "ticker": "AAPL",
      "close": null,
      "volume": 12969829.0,
      "return_1d": null,
      "return_5d": null,
      "return_20d": null,
      "benchmark_return_20d": null,
      "timestamp": "..."
    }
  }
}
```

## Ostatnio znane rekordy

- `2026-06-16T15:56:49.328327Z` — snapshot z `AAPL`, `MSFT`, `SPY`.
- `2026-06-16T19:10:30.248326+00:00Z` — snapshot z pełną watchlistą.
- `2026-06-16T20:14:21.937071+00:00Z` — snapshot z pełną watchlistą.

## Uwagi

W dostępnych rekordach ceny `close` są `null`, więc skaner nie ma aktualnie danych do obliczenia momentum.

## Linki

- [[Market Data Flow]]
- [[Reporting and Persistence]]
- [[Results Directory]]
