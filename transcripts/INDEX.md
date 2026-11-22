# D5 — Session transcript index

One **main** OpenCode session per member (raw export), plus an index. Secondary
sessions go under `transcripts/appendix/` (not a substitute for the main session).
Annotation format for human interventions: **execution_plan §10.1**
(`HUMAN-INTERVENTION` · time · type ∈ {interrupt, redirect, approve, reject} ·
reason · affecting REQ/ADR/INV).

| Member | Main transcript file | AI-use log session_id | Covers PR / REQ | Status |
|---|---|---|---|---|
| A (yuxiangdu39) | `transcripts/<student-id>-<name>.md` — *to be provided* | in `docs/ai-use-log.yaml` (A entries) | FR-01 pack #25 / INV-02 spec #4 | **PENDING (A to submit)** |
| B (cosine-Y) | `transcripts/<student-id>-<name>.md` — *to be provided* | in `docs/ai-use-log-B-fragment.yaml` (`ses_e0451298…`) | FR-02 budget, PR #22 | **PENDING (B to submit)** |
| C (wawfggqq) | `transcripts/<student-id>-<name>.md` — *to be provided* | *(none on main — needs an AI-use entry)* | C modules (deliberation/prompts) | **PENDING — no AI-use log yet** |
| D (ZFebron491001) | `transcripts/<student-id>-<name>.md` — *to be provided* | in `docs/ai-use-log-D-fragment.yaml` (D-* entries) | FR-04 risk_gate, PR #20 | **PENDING (D to submit)** |
| **E (61069361 ZHOU Jianmin)** | `transcripts/61069361-ZHOU-Jianmin.md` (complete) + `…raw.json` (authoritative) + `…-annotations.md` | `ses_e095275cbffeefLAOdxMbkW2QF` (main); 6 log sessions (below) | FR-05 contracts + E2 + CI/gov: PR #3, #8, #11, #12, #18, #23 | **PARTIAL** (raw+annotations done; pending D acceptance/freeze) |

## E — main session
- File (complete Markdown): `transcripts/61069361-ZHOU-Jianmin.md`
- File (authoritative raw JSON): `transcripts/61069361-ZHOU-Jianmin.raw.json`
- Annotations: `transcripts/61069361-ZHOU-Jianmin-annotations.md`
- OpenCode session: `ses_e095275cbffeefLAOdxMbkW2QF` — “Group assignment review for role E”
- Exported via `opencode export <sessionID>` (real); complete (non-truncated) render, **1260 messages**.
- `export_sha256` (= **Markdown** transcript sha): `533e63760cd17c74f6fa26a9c9ad0c6d9c77ddea1fe83453a109a0a6db66112a`
- `raw_export_sha256` (= **raw JSON** export sha, redacted): `007caf575072bf32736a0aed67e8c8222ba69e70b0706994a55a2f22793c980e`

## E — phase index (which log session covers which work)
| Log session_id | Phase | PR / requirement |
|---|---|---|
| `E-2026-11-20-spec-FR05-batchA` | FR-05 spec (Batch A) | #3 · FR-05, NFR-08, NFR-09 |
| `E-2026-11-20-spec-FR05-batchB` | FR-05 spec (Batch B) | #3 |
| `E-2026-11-21-spec-FR05-final` | FR-05 convergence | #3 |
| `E-2026-11-21-spec-FR05-converge` | FR-05 threshold contract | #12 |
| `E-2026-11-21-spec-E2-evaluation` | E2 spec | #8 · NFR-08 |
| `E-impl-FR05-contracts-v3` | FR-05 contracts v3 + E2 impl | #18 · GATE-01 |

## Notes
- **This PR covers only the E part; D5 is NOT complete until A/B/C/D submit.**
- **PR #23** (DEBT-FR05-D4 close + budget CI suite + #10 supersede record) is still **open** (not yet merged); the budget suite there is N/A until FR-02 impl + record.
- `transcripts/**` is **not** part of any `spec_bundle` (FR-05/E2) → no hash/bundle recompute.
- Others' rows are **not** filled on their behalf; they submit their own file + log entry.
- C currently has **no** AI-use log entry on `main` — C must create one.
