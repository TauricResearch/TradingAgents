# PR28: Explainable Game Opportunity Radar

## Purpose

PR28 turns the game-company catalog and approval cache into a repeatable
attention screen for Perfect World (`002624`) and Century Huatong (`002602`).
It is not a recommendation model: it does not emit a trade direction, target
price, position size, or risk approval.

## Four independent factors

Each factor contributes zero to three points and retains its own metrics,
observation date, source links, and explanation.

| Factor | Supportive observations |
| --- | --- |
| Official approvals | Exact company-linked approval within 90/180 days and multiple approvals within 365 days |
| Product catalysts | Upcoming launches plus ongoing or undated tracked product work |
| Financial delivery | Positive net-profit growth and positive reported operating cash flow |
| Market confirmation | Positive 20-session and 60-session cached price returns |

The total score maps to `high_attention` (8-12), `watch` (5-7), or
`low_signal` (0-4). Missing financial or market data forces
`insufficient_data`, regardless of the partial score.

## Point-in-time rules

- Price bars and fundamentals must have been available by the requested date.
- Approvals must satisfy their `available_as_of` boundary.
- Product catalysts come from the date-filtered PR26 company snapshot.
- A missing approval cache is different from a present cache with zero exact
  company matches.

These rules make historical radar results reproducible and prevent later
approvals or disclosures from leaking into an earlier view.

## Cockpit and API

The ticker snapshot now includes `game_opportunity`, rendered as a four-row
factor panel. `GET /api/game-opportunities` returns the covered universe ordered
by attention score and then symbol.

The radar remains isolated under `tradingagents.research_platform`; it does not
modify the legacy graph, agent prompts, deterministic risk engine, or archived
trade decisions.
