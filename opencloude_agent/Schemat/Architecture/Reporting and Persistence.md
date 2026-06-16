---
type: architecture
tags:
  - opencloude-agent
  - reporting
---

# Reporting and Persistence

[[ReportWriter]] odpowiada za zapis wyników agenta.

## Katalog wyników

Domyślnie:

```text
results/continuous/
```

## Pliki

- `watch_log.jsonl` — snapshoty rynku.
- `opportunities.jsonl` — znalezione okazje.
- `decisions.jsonl` — decyzje paper-tradingowe.
- `daily_summary.md` — podsumowanie cyklu.
- `log.txt` — tekstowy log cykli.

## Metody

- `append_jsonl(filename, payload)` — dopisuje JSON do JSONL.
- `append_text(filename, line)` — dopisuje linię tekstu.
- `write_daily_summary(report)` — zapisuje Markdownowe podsumowanie.

## Linki

- [[ReportWriter]]
- [[Results Directory]]
- [[Daily Summary]]
- [[Watch Log]]
