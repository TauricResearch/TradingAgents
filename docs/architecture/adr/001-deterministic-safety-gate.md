# ADR 001 — Deterministic Safety Gate after the Portfolio Manager

- Status: Accepted (experiment slice)
- Context: CS5351 agentic-SE trial on TradingAgents; human chooses architecture and
  invariants, AI implements only after approval.

## Problem
The final decision is an LLM-backed Portfolio Manager output that flows straight to
END (`tradingagents/graph/setup.py`: `Portfolio Manager -> END`). Unreadable ratings
already fail closed to `REVIEW` in `tradingagents/agents/rating.py`, so re-parsing is
not the gap. The gap is (a) no deterministic authority separating "LLM proposes" from
"system authorizes", and (b) no evidence-completeness invariant: a tradeable rating can
exit even when configured analysts contributed nothing or required plans are empty.

## Candidates
- A. Baseline: raw final decision, no post-check.
- B. Guarded hybrid: one deterministic Safety Gate node after the Portfolio Manager,
  before END (no model call).
- C. Extra LLM critic/reviewer node after the Portfolio Manager.

## Observable scoring (1 = strong, 0 = weak)
| Criterion | A | B | C | Critical? |
|---|---|---|---|---|
| Invariant protection | 0 | 1 | 0.5 | yes |
| Authority separation | 0 | 1 | 0 | yes |
| Fail-closed | 0.5 | 1 | 0 | yes |
| No extra LLM runtime | 1 | 1 | 0 | yes |
| Evidence completeness | 0 | 1 | 0.5 | no |
| Compatibility | 1 | 1 | 0.5 | no |
| Testability | 0.5 | 1 | 0.5 | no |
| Latency | 1 | 0.9 | 0.3 | no |
| Token cost | 1 | 1 | 0.4 | no |
| Coupling/cohesion | 0.5 | 1 | 0.4 | no |
| Impl complexity | 1 | 0.8 | 0.3 | no |

## Decision
Critical drivers act as elimination filters, not a sum. A fails invariant protection,
authority separation, and fail-closed. C fails authority separation, fail-closed, and
no-extra-LLM-runtime. **Only B passes every critical driver**, and it is the smallest
guarded-hybrid, so **Candidate B** is adopted.

## Consequences
- Positive: deterministic authority at the decision boundary; evidence completeness
  enforced; machine-readable reason codes; zero added tokens; offline-testable.
- Negative: one extra graph step; partial runs are held for REVIEW (accepted);
  checkpoint signature gains `safety=gate`, invalidating pre-change checkpoints.
- Runtime fallback: any gate exception yields REVIEW / GATE_ERROR, never a tradeable
  rating.

## Reopen triggers
- A measured need for semantic evidence (citation) that existence checks cannot meet.
- Evidence the strict existence check pushes REVIEW rate unacceptably high in normal
  full selections (note: complete selections pass through unchanged).
- A product requirement for a second, independent model opinion (would justify C only
  with measured benefit exceeding its token and failure surface).
