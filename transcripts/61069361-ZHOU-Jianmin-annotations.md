# E — Human-intervention annotation index (D5)

Companion to `transcripts/61069361-ZHOU-Jianmin.md` (raw: `…raw.json`). This file
does **not** modify the raw session; it indexes the human interventions found in
it. Format per `execution_plan` §10.1: **time · type (interrupt|redirect|approve|
reject) · reason · affects (REQ/ADR/INV) · original message (timestamp + verbatim
opening)**. All timestamps are from the exported session (UTC), verbatim openings
are quoted from the real user turns — nothing fabricated.

## Approvals
| time | type | reason | affects | original message (verbatim opening) |
|---|---|---|---|---|
| 2026-11-20T02:08:41Z | approve | Approved contract draft commit | FR-05, GATE-01 | “Approve. The code is perfect. Please help me execute git add and git commit…” |
| 2026-11-20T03:45:34Z | approve | Approved test plan with 3 conditions | FR-05, GATE-01 | “Plan approved with 3 conditions. Address these before/with implementation…” |
| 2026-11-20T03:52:36Z | approve | Accepted 34-green tests; env flagged as defect | NFR-08 | “Test 34: Green, src zero logic changes, honest reporting environment, approved. However…” |
| 2026-11-20T04:22:16Z | approve | Approved CODEOWNERS decisions | GATE-01 | “Three decisions will be implemented as follows: 【1 CODEOWNERS】Approved…” |
| 2026-11-21T05:50:21Z | approve | D approved PR #3 (GATE-01 spec closed loop) | FR-05, GATE-01 | “D has approved PR #3 (GATE-01 closed loop). Now…” |
| 2026-11-21T12:19:55Z | approve | Approved v3 plan; Phase 2 in same PR | GATE-01, NFR-08 | “Stage 1: Plan approved. Phase 2 (src/egta/evaluation/*) accepts this PR…” |
| 2026-11-21T15:56:55Z | approve | A approved #11 (pre-merge confirm) | D7 | “A has approved PR #11. Proceed with confirmation before merging…” |
| 2026-11-22T03:42:59Z | approve | D+B dual-approved #12 | FR-05 | “B has officially approved #12 … D has also been approved…” |
| 2026-11-22T03:47:06Z | approve | Approved v3 execution plan | FR-05, GATE-01 | “v3 plan approved. Execution: 1. Create impl/FR-05-contracts-v3…” |
| 2026-11-22T07:36:00Z | approve | Approved finalization plan (one PR, budget suite) | DEBT-FR05-D4, D7 | “Plan approved, Decision: 1. One PR … 2. Add budget suite now…” |

## Rejections / changes-requested (D’s reviews acted on)
| time | type | reason | affects | original message (verbatim opening) |
|---|---|---|---|---|
| 2026-11-20T10:21:24Z | reject | D: #1 violates GATE-01 (impl before tests) → refactor | GATE-01, FR-05 | “D requested changes for PR #1 (GATE-01 timing issue: implementing fff66d0 earlier than test 7df4489)…” |
| 2026-11-20T13:37:15Z | reject | D changes on #3 (spec incomplete) | FR-05 | “D has requested changes to PR #3 … B has replied…” |
| 2026-11-21T03:39:01Z | reject | D 14-item final review on #3 | FR-05, GATE-01 | “D conducted the final round of review for PR #3 (14 items)…” |
| 2026-11-21T04:46:48Z | reject | D 10 convergence tasks (e00b609) | FR-05 | “The final round of review (e00b609, “close but not approvable”) involved 10 convergence tasks…” |
| 2026-11-21T07:45:39Z | reject | D 8 changes on #6 | FR-05 | “D made 8 Request changes to PR #6…” |
| 2026-11-21T09:40:46Z | reject | D 5 rulings on #8 contract-change | FR-05 | “D has ruled on all 5 items and has begun to implement PR#8…” |
| 2026-11-21T13:22:26Z | reject | A 3 blocks + minor on #11 | D7 | “A reviewed CI PR #11 and gave 3 blocks + minor…” |
| 2026-11-21T14:43:32Z | reject | #11 more points + #12 registry count | D7, FR-05 | “Review #11 raised two more points, and #12 requires updating the registry count…” |
| 2026-11-21T15:16:59Z | reject | A: FR-01 package not installable in #11 | DEBT-FR01-CI | “Review #11 (ef913f0): … FR-01 evidence package cannot be installed…” |
| 2026-11-21T15:21:08Z | reject | #12 doc defect (spec-registry-E2 fragment) | FR-05 | “Review #12 (ba5c59f) has only one remaining document defect…” |
| 2026-11-21T15:39:46Z | reject | #11 3 debt text fixes | DEBT-FR01-CI, D7 | “Review #11 (7f90834): The gate code has been approved. There are only 3 debt…” |
| 2026-11-21T15:47:27Z | reject | D: #12 7 bindings + 213→223 note | FR-05 | “A has approved #11; D said to #12 (68038eb) … 7 inconsistencies…” |
| 2026-11-21T16:09:42Z | reject | D: #12 conflicts main, merge (no rebase) | FR-05 | “D pointed out for #12(ee68ac1): … #12 conflicts with main … must merge main…” |
| 2026-11-22T05:48:36Z | reject | D: #18 3 mandatory + 5 suggestions | FR-05, NFR-06 | “For #18 (798e9f5), I propose 3 mandatory and 5 suggestions…” |
| 2026-11-22T10:04:34Z | reject | Security: PAT prefix in transcript → redact | INV-07 | “#28's … line 376 contains a prefix of the github_pat_ token… Immediately…” |
| 2026-11-22T10:06:28Z | reject | D: #28 D5 content incomplete (raw+annotations) | GATE-06 | “#28 D5 Content Rectification (as required by D): 1. Re-export the complete raw session…” |

## Corrections / redirects
| time | type | reason | affects | original message (verbatim opening) |
|---|---|---|---|---|
| 2026-11-20T03:52:36Z | redirect | Reject temp venv; require real egta env | NFR-08, DEBT-D1 | “…the environment is a project defect must be addressed…” (→ rerun in egta) |
| 2026-11-20T04:09:08Z | redirect | Rerun in conda `egta` (12.16) | NFR-08 | “The conda egta environment has been successfully set up (Python 3.12.16…)…” |
| 2026-11-21T03:48:06Z | redirect | Fix PENDING contradiction (B resolved) | FR-05 | “Before concluding, let's correct a contradiction: You ended with “PENDING: (B)…” |
| 2026-11-21T08:17:01Z | redirect | 29≠27 number consistency correction | FR-05 | “Very good. The assumption of “positive intervention” … 1. [Consistency of numbers]…” |
| 2026-11-21T13:39:47Z | redirect | Don’t update #11 yet (A mid-review) | D7 | “#11's EXPECT_CONTRACTS=199 will become outdated after #12 … Do not make the…” |
| 2026-11-21T14:26:44Z | redirect | State 213→223 explicitly (A5 +10) | FR-05 | “The change from 213 to 223 (A5 operator boundary +10) should be clearly stated…” |
| 2026-11-21T15:01:34Z | redirect | Re-execute per D’s exact definition (not simplified) | FR-05 | “The plan has been approved, but it will be re-executed after correcting 4 points…” |
| 2026-11-22T06:13:26Z | redirect | #18 BEHIND → merge main, no rebase | FR-05, GATE-01 | “#18 As main moved forward, it became BEHIND … merge origin/main … Do not rebase.” |
| 2026-11-22T07:05:52Z | redirect | #18 diverged → sync (a), then merge | GATE-01 | “First, just check if #18 is still BEHIND … If still BEHIND/diverged → Proceed with synchronization (a).” |
| 2026-11-22T10:02:18Z | redirect | INDEX nit (A covers → #25/#4) + #23 note | D5 | “Approval #28: A non-blocking nit needs to be changed …” |

## Waits / interrupts (agent correctly stopped for authorization)
| time | type | reason | affects | original message (verbatim opening) |
|---|---|---|---|---|
| 2026-11-20T02:57:46Z | interrupt | GATE-01: wait for human before commit/PR | GATE-01 | “E1 (Day1 Contract) has been branched … You are the executor, and all the git/gh/code should be completed by you. I will only approve…” |
| 2026-11-20T03:19:33Z | interrupt | gh unauthenticated → wait for auth | GATE-01 | “GH has been authenticated … Proceed to stage A…” (agent had stopped when not authenticated) |
| 2026-11-20T03:38:56Z | interrupt | PAT lacked PR scope → wait for classic token | GATE-01 | “GH has been authenticated using the classic token (repo scope)…” |
| 2026-11-20T04:35:51Z | interrupt | GitHub API TLS (WATT) outage → wait/retry policy | — | “Watt has been shut down. The gh REST service should be restored…” |
| 2026-11-21T10:04:39Z | interrupt | Process rule: PR comments must @D/@B | GATE-06 | “From now on, all PR comments must @mention the relevant parties…” |
| 2026-11-21T11:23:13Z | interrupt | Post-approval freeze: no more pushes (#8) | GATE-01 | “PR#8 head 5550f9d has been approved by D … no more push is allowed…” |
| 2026-11-22T03:50:23Z | interrupt | Formal-record rule: notify via PR comments | GATE-06 | “From now on, all notification messages will be posted as comments…” |

## Notes
- The full set of **105** human turns is in the complete transcript; this index
  highlights the **approve/reject/correct/wait** events D asked for.
- Line anchors: each intervention corresponds to the `## [user] <time>` header in
  `transcripts/61069361-ZHOU-Jianmin.md` (search by the timestamp above).
- No event was invented; every row quotes a real user turn.
