# PR25: Local Decision Journal

PR25 adds a personal decision journal without changing archived research
reports or connecting to a broker.

## What it records

- A chosen archived run and its manual `TradeSignal`.
- Direction, horizon, confidence, position proposal, rationale, and invalidation triggers.
- The most recent locally available closing price on the decision date.
- A user-selected review due date.
- One explicit review with a local reference price, market return, directional return, and optional note.

The journal lives in `<data-dir>/decision_journal.json`. Research runs remain
immutable under `<data-dir>/runs/`.

## Cockpit workflow

1. Run research with a manual decision in the **Decision Draft** panel.
2. Select that archived run in **Research Runs**.
3. Set a review due date in **Decision Journal** and choose **Journal Selected Decision**.
4. On or before the intended review date, set **Review Date**, add an optional note, and choose **Record Review** on the journal entry.

Only one journal entry may be created for an archived run. This avoids turning
repeated button clicks into duplicate personal decisions.

## Data discipline

- Entry prices are selected from the archived run snapshot (with the local
  cache as an eligible fallback) and must have been available by the decision
  date.
- Review prices are selected only from cached bars dated and available on or
  before the selected review date.
- `Buy` and `Hold` directional return equals the underlying market return.
  `Sell` directional return is calculated as `entry_price / review_price - 1`.
- A journal return is a research-review measurement, not an execution record,
  tax calculation, or broker P&L.

## HTTP endpoints

- `GET /api/decision-journal?symbol=600519`
- `POST /api/decision-journal`
  ```json
  {"symbol":"600519","run_id":"<local-run-id>","review_due_date":"2026-10-10"}
  ```
- `POST /api/decision-journal/<entry-id>/review`
  ```json
  {"reviewed_on":"2026-10-10","note":"Optional review note."}
  ```

All endpoints are local-only and operate on the configured Cockpit data
directory.
