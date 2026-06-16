---
type: runtime
tags:
  - opencloude-agent
  - cli
---

# CLI Entry Points

Projekt można uruchamiać jako pakiet Python.

## Jednorazowy cykl

```bash
python -m opencloude_agent.run
```

## Pętla ciągła

```bash
python -m opencloude_agent.run --watch
```

## Pętla z własnym interwałem

```bash
python -m opencloude_agent.run --watch --interval-seconds 1800
```

## Własna watchlista

```bash
python -m opencloude_agent.run --watchlist AAPL,MSFT,NVDA
```

## Własny katalog wyników

```bash
python -m opencloude_agent.run --results-dir results/my-run
```

## Linki

- [[Configuration and Defaults]]
- [[Results Directory]]
- [[Agent Loop]]
