---
type: runtime
tags:
  - opencloude-agent
  - results
---

# Results Directory

Wyniki działania agenta trafiają do katalogu:

```text
results/continuous/
```

## Pliki

- [[Daily Summary]] — bieżące podsumowanie w Markdown.
- [[Watch Log]] — log snapshotów rynku w JSONL.
- `log.txt` — tekstowy log cykli, okazji i decyzji.
- `opportunities.jsonl` — zapisane okazje.
- `decisions.jsonl` — zapisane decyzje.

## Przykładowe podsumowanie

Aktualny plik `daily_summary.md` zawiera sekcje:

- Risk level.
- Portfolio.
- Opportunities.
- Decisions.

## Linki

- [[Reporting and Persistence]]
- [[CLI Entry Points]]
- [[Configuration and Defaults]]
