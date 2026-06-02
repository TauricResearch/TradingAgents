# Research Registry

Canonical index of all investment research documents. Each entry links to watchlist candidates via `research_doc` field.

---

| ID | Document | Date | Sector | Tickers | Status |
|----|----------|------|--------|---------|--------|
| `hormuz-2026-05-14` | [Hormuz Bottleneck Recovery Stock Analysis](prospects/hormuz-recovery-2026-05-14.md) | 2026-05-14 | Energy (Upstream E&P, Integrated), Industrial Gas (Helium), Fertilizer, Defense | COP, FANG, LIN, APD, CF, MOS, LMT, RTX, GD, SHEL, CVX, BP | active |

---

## Adding New Research Documents

When adding a new research document:

1. Create the document in `docs/` (e.g. `docs/My-Research-Title.md`)
2. Add an entry to this registry with:
   - **ID:** `YYYY-MM-DD`-slug of the document title (lowercase, hyphens)
   - **Document:** Human-readable title + link to the file
   - **Date:** ISO date the document was created
   - **Sector:** Comma-separated sector tags
   - **Tickers:** Comma-separated list of all companies mentioned in the research
   - **Status:** `active` (ongoing research) or `archived` (superseded)

3. When seeding stocks to the watchlist, set `research_doc` to match the entry ID

## Stale Research

Entries older than 90 days with no watchlist activity are flagged as stale (`⚠` in the CLI).
To refresh: re-run the analysis or update `last_research_update` in the watchlist table.

## Source URLs

| Research Doc | Source |
|--------------|--------|
| hormuz-2026-05-14 | `docs/prospects/hormuz-recovery-2026-05-14.md` |