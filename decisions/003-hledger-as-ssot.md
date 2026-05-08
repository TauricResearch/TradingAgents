# Decision: hLedger as Single Source of Truth for Positions

**Date:** 2026-05-02
**Status:** Accepted

## Context

The project inherited a SQLite `positions` table from the initial dashboard build. But the operator already used hLedger for plain-text accounting — all trades, cash balances, and asset holdings were tracked in `~/.hledger.journal`. Maintaining two sources of truth (SQLite + hLedger) created drift: a position could be in hLedger but missing from SQLite, or vice versa.

## Decision

hLedger is the single source of truth for all accounts, positions, and cash. SQLite stores AI artefacts (signals, analyses, watchlist, prices) and operational data — but never duplicates what hLedger owns. The dashboard reads hLedger via subprocess; it never writes to it.

## Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| SQLite as SSOT, hLedger as export | Would require bidirectional sync — fragile and complex; hLedger already had the operator's trust |
| SQLite only, drop hLedger | hLedger's plain-text format is human-readable, git-diffable, and tool-independent; operator workflow already built around it |
| Dual-write to both | Guaranteed eventual inconsistency; "two sources of truth is no truth" |

## Consequences

**What became easier:**
- No position sync bugs — hLedger IS the position
- hLedger's `balance`, `register`, `prices` subcommands provide free query capability
- Plain-text journal is git-versioned independently
- Dashboard can show real-time cash + position data without maintaining its own ledger

**What became harder:**
- Every position view requires a subprocess call to hLedger (cached in memory, but adds startup latency)
- hLedger output parsing is fragile — text-based, locale-dependent, requires edge-case handling
- Adding a new account type means updating both the hLedger journal AND the SQLite accounts table

**Constraints this imposes:**
- Never write to hLedger from the dashboard (read-only contract)
- `src/server/lib/hledger.ts` is the only file that calls hLedger
- SQLite `positions` table is deprecated — kept for historical data only
- All position queries go through `hledger.ts`, not `db.ts`

## Related

- Debrief: `debriefs/debrief-dashboard-foundation-2026-05-02.md`
- Playbook: `playbooks/hledger-playbook.md`
- ADR: `decisions/004-database-factory-singleton.md` (SQLite role)
