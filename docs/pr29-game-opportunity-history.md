# PR29: Game Opportunity History and Change Events

## Purpose

PR29 makes the PR28 radar trackable over time. A current score is useful for
screening; a persisted daily series answers the more important questions:
what changed, when did it change, and which underlying factor caused it?

## Persistence

`JsonGameOpportunityHistory` stores one JSONL file per covered symbol under
`game_opportunity_history/`. Each calendar date has at most one snapshot:

- rerunning the same date is idempotent when inputs are unchanged;
- corrected same-day inputs replace that date rather than append duplicates;
- historical insertion and point-in-time reads remain date ordered;
- writes use a temporary file followed by an atomic replace.

## Change events

The deterministic comparison layer emits:

- `baseline_created` for the first observation;
- `level_changed` when attention classification changes;
- `score_changed` when the total moves;
- `factor_changed` for an individual factor score move;
- `new_approval` when the exact 365-day approval count increases, even if the
  approval factor was already at its maximum score.

Events describe research-state changes only. They do not create trades,
positions, notifications, or risk approvals.

## Usage

```powershell
python -m tradingagents.research_platform.game_opportunity_track_cli `
  --data-dir .runshots `
  --as-of 2026-07-12
```

The command records the covered universe and prints each company level, score,
and newly detected events as JSON. It is suitable for a user-managed operating
system scheduled task; PR29 does not install a background service.

## Cockpit

The ticker snapshot includes `game_opportunity_history`. The Opportunity
Changes panel shows the latest comparison events and up to eight recent daily
scores. `GET /api/game-opportunity-history?symbol=...` exposes the same local
history as JSON.
