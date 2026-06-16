---
type: structure
tags:
  - opencloude-agent
  - repository
---

# Repository Structure

## Katalog główny

```text
opencloude_agent/
├── __init__.py
├── run.py
├── tests/
│   └── test_opencloude_agent.py
├── results/
│   └── continuous/
│       ├── daily_summary.md
│       ├── log.txt
│       └── watch_log.jsonl
└── Schemat/
    └── ...
```

## Pliki źródłowe

- [[../Code/run.py]] — główna implementacja agenta, modeli, raportowania i CLI.
- [[../Code/__init__.py]] — eksport publiczny pakietu.

## Testy

- [[../Tests/test_opencloude_agent]] — testy jednostkowe dla portfela, skanera, risk guardia, raportów i market watchera.

## Wyniki działania

- [[../Results/Continuous/Daily Summary]] — aktualne podsumowanie cyklu.
- [[../Results/Continuous/Watch Log]] — indeks/log obserwacji rynku.
- `results/continuous/log.txt` — tekstowy log cykli, okazji i decyzji.
- `results/continuous/opportunities.jsonl` — okazje zapisywane jako JSONL, gdy agent je znajdzie.
- `results/continuous/decisions.jsonl` — decyzje zapisywane jako JSONL, gdy agent je wygeneruje.

## Sejf Obsidian

- [[../CLAUDE.md]] — zasady pracy w sejfie.
- [[../00-Index]] — punkt wejścia do dokumentacji.
- [[../Zapiski/Claude_Log]] — rejestr decyzji.

## Uwagi

Repozytorium Git nie jest wymagane do działania tego projektu. W tej lokalizacji projekt istnieje jako katalog pakietu Python z plikami źródłowymi, testami i wynikami.
