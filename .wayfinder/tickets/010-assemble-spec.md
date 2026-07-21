---
id: 010
title: "Task: assemble the implementation spec"
labels: [wayfinder:task]
status: closed
assignee: JMAN730
blocked-by: [008, 009]
---

## Question

Consolidate every closed ticket's resolution into one implementation spec — the destination artifact. Not new decisions: pure assembly, resolving any small contradictions between tickets in favor of the later/more-verified resolution (002 vs 005 SSE phrasing already reconciled in 005).

Deliverable: `docs/web-ui-spec.md` (or location the repo prefers) covering: architecture overview, API surface (endpoints, SSE event schema), run manager design, frontend structure, security requirements (CSP, Host allowlist, key handling — verbatim from 004/007), packaging/entry-point changes, Docker changes, testing plan, and an ordered implementation plan (suitable for /writing-plans or direct execution). Include the decisions-so-far links for traceability. Reports the fog leftovers (live price charts nice-to-have) as explicit non-goals/v2 candidates.

## Resolution

Spec written: `docs/web-ui-spec.md` — 13 sections: architecture, packaging/entry point, API surface + SSE event schema, run manager, frontend, security requirements, history/persistence, config, Docker, testing, ordered 9-step implementation plan (steps 3–6 ∥ 7 after 2), non-goals/v2, traceability table linking all nine closed tickets. Pure consolidation; no new decisions. The 002-vs-005 SSE phrasing conflict was already reconciled in 005 (run task decoupled from SSE generator) and the spec records the reconciled form.
