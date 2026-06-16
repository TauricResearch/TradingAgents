---
type: code
tags:
  - opencloude-agent
  - python
  - main-module
---

# run.py

Plik `run.py` zawiera główną implementację agenta.

## Definicje i klasy

- `DEFAULT_WATCHLIST = ["AAPL", "MSFT", "NVDA", "TSLA", "SPY"]`
- `utc_now()` — zwraca aktualny czas UTC.
- `Opportunity` — rekord okazji z tickerem, wynikiem, uzasadnieniem i snapshotem.
- `PaperPortfolio` — symulowany portfel z gotówką i pozycjami.
- `MarketWatcher` — pobiera dane z `yfinance` i buduje snapshot rynku.
- `OpportunityScanner` — sortuje tickery po score i ogranicza liczbę kandydatów.
- `RiskGuard` — ocenia ryzyko portfela i brak okazji.
- `ReportWriter` — zapisuje JSONL, log tekstowy i podsumowanie Markdown.
- `OpenClaudeContinuousAgent` — koordynuje cykl działania.
- `build_parser()` — buduje parser CLI.
- `main()` — uruchamia jednorazowo albo w pętli.

## Najważniejsze zależności

- `yfinance` — pobieranie danych rynkowych.
- `pandas` — obsługa ramki danych.
- `argparse` — CLI.
- `dataclasses` — modele danych.

## Linki

- [[Package Overview]]
- [[Agent Loop]]
- [[Market Data Flow]]
- [[Opportunity Scoring]]
- [[Risk Evaluation]]
- [[Paper Portfolio]]
- [[Reporting and Persistence]]
- [[CLI Entry Points]]
