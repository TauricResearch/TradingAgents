# Prospect Lists

Canonical source for all stock purchase prospect lists. These documents feed the Python `tradingagents` analysis pipeline.

---

## Source Documents

| ID | Document | Date | Tickers | Theme |
|----|----------|------|---------|-------|
| `hormuz-2026-05-14` | [Hormuz Recovery](hormuz-recovery-2026-05-14.md) | 2026-05-14 | COP, FANG, DVN, LIN, APD, CF, MOS, LMT, RTX, GD, CVX, SHEL | Hormuz chokepoint beneficiaries (energy, industrial gas, fertilizer, defense) |
| `felix-prehn-2026-05-15` | [Felix Prehn Picks](felix-prehn-picks-2026-05-15.md) | 2026-05-15 | NEM, CCJ, FCX, SCCO, TTE, AVGO, FIX, STX, CLS, RKLB, RTX, MTZ, PWR | Multi-sector quality/growth framework (gold, uranium, copper, energy, chips, infra, defense) |
| `great-rotation-2026-05-14` | [Great Rotation Report](great-rotation-2026-05-14.md) | 2026-05-14 | NEM, CCJ, FCX, TTE, AVGO, FIX, STX, RKLB, PWR | Goat Academy quality stocks (9 names, overlaps with Felix Prehn) |
| `nuclear-2026-05-29` | [Nuclear Power](nuclear-power-2026-05-29.md) | 2026-05-29 | NNE, OKLO, SMR, VIGR, VRT | Small modular reactors, power conversion, infrastructure |

---

## Consolidated View

The [combined-prospects.json](combined-prospects.json) file provides a machine-readable consolidation of all tickers across all sources. It is the primary input for the Python `tradingagents` analysis pipeline.

**Total unique tickers:** 38

## Updating

When adding a new prospect list:

1. Create the document in this directory: `docs/prospects/<slug>.md`
2. Add an entry to the table above with ID, link, date, tickers, and theme
3. Regenerate `combined-prospects.json`:

   ```bash
   just prospects-build
   ```

   Or manually with the build script:

   ```bash
   bun run scripts/prospects-build.ts
   ```

## Python Integration

The Python `tradingagents` package reads `combined-prospects.json` to load the prospect universe for analysis. The file structure is:

```json
{
  "version": "1.0",
  "sources": [{ "id": "...", "name": "...", "document": "..." }],
  "tickers": [
    { "ticker": "...", "source": "...", "sector": "...", "thesis": "..." }
  ]
}
```

The `tradingagents` package loads this at startup and uses it as the default analysis universe when no specific ticker is provided.
