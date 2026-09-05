# PR27: NPPA Game Approval Tracking

## Scope

This increment adds an isolated, official-source approval pipeline for the two
A-share game-company profiles introduced in PR26. It does not alter the legacy
TradingAgents graph or use approvals as automatic investment signals.

## Data flow

1. `NppaApprovalProvider` discovers dated pages from the official domestic and
   imported online-game approval indexes.
2. Table rows are normalized into immutable `GameApprovalRecord` contracts.
3. `JsonGameApprovalStore` atomically merges records into
   `game_approvals/approvals.jsonl` under the selected local data directory.
4. `match_game_approval` attributes a record only when its publisher or operator
   exactly matches a curated legal entity. Brand-like but unknown names are
   marked `review_required`; unrelated rows remain `unmatched`.
5. The cockpit snapshot and `GET /api/game-approvals?symbol=...` expose exact
   matches for a selected company.

## Covered legal entities

- `002602`: Shanghai Shulong and Shengqu Information legal entities, supported
  by Century Huatong company filings.
- `002624`: Perfect World game-development legal entities listed by the
  company's official privacy/affiliate disclosure.

The aliases are deliberately narrow. Expanding them requires an official source
and a test; fuzzy matching must never create an automatic company attribution.

## Usage

```powershell
python -m tradingagents.research_platform.game_approval_sync_cli `
  --data-dir .runshots `
  --start 2026-01-01 `
  --end 2026-07-12
```

Use `--kind domestic`, `--kind imported`, or `--dry-run` to limit the operation.
The command prints record, match-status, and covered-symbol counts as JSON.

## Source boundaries

- Approval facts come only from the National Press and Publication
  Administration pages.
- Listed-company relationships come from official company disclosures.
- `available_as_of` prevents a page or row from appearing before its publication
  or approval date in point-in-time reads.
