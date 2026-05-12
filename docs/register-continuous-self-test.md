# The Register as Continuous Self-Test

*Design principle — 2026-05-11*

---

## The Loop

```
just check
    ↓
registers verify invariants
    ↓
drift detected → signal to stop
    ↓
agent fixes → reassert integrity
    ↓
known-good state
    ↓
trust → cross-reference with confidence
    ↓
just check (repeat)
```

This is not a documentation system. This is a self-referential integrity loop.

---

## What `just check` Actually Is

Most projects have a check command — lint, typecheck, test. It's narrowly scoped: it checks the code, and it stops there. You run it to know if you're broken.

`just check` is different. It checks code AND registers. The code check is the primary concern — TS compiles, biome lints, DB usage is clean. But because it's fast, it also checks everything else: briefs, debriefs, decisions, playbooks, docs, blog. All the registers. All at once.

The consequence: **you never ship with unknown state**.

Every time you run `just check`, you're confirming that the entire project — code and knowledge base — is coherent. If anything drifts (a new brief not indexed, a debrief orphaned, a code file missing from the register), you know immediately.

---

## The Agent as Maintenance Operator

When the register reports an inconsistency — or when the agent observes one — it doesn't ignore it. It stops. It fixes. It reasserts the invariants.

This is the difference between a passive documentation system and an active integrity system:

| Passive | Active |
|---------|--------|
| Drifts until someone notices | Drift detected and fixed as it happens |
| Human must remember to check | Check runs on every `just check` |
| Ambiguities unresolved | Canonical source resolves ambiguities |
| Partial knowledge | Known-good state |

The agent is the maintenance operator in the loop. It runs `just check`, observes the output, fixes drift, and moves on.

---

## Why Fast Matters

A slow check wouldn't work. You'd run it for the code and skip it for the registers. A separate register check would be ignored — "I'll do it later." But a fast check that does both? That's the design.

The code check funds the register check. You have to run `just check` anyway. Because it's fast, you can check everything else without it being a burden. The two are bundled because they can be, not because they must be.

If `just check` took 30 seconds, you'd skip the register checks. The integrity loop breaks. The system drifts.

---

## The Epistemological Point

When the registers are clean, you have a known-good state:

- **You know what you have** — code indexed, files tracked, schemas verified
- **You know what you know** — briefs and debriefs are current, decisions are recorded
- **Cross-referencing is reliable** — no drift between "what the docs say" and "what the code has"

When the registers are dirty, you don't know what you don't know. You're working with partial information. Ambiguities can't be resolved because there's no canonical source to check.

The integrity of the registers is the integrity of your knowledge of the system. `just check` is the test. The agent is the fix. The registers are the invariants.

---

## Signals That Trigger a Stop

Any of these is a signal to stop and reassert register integrity:

- `just check` fails on a register drift (MISSING or STALE entry)
- Agent observes a gap between what's documented and what exists
- A new directory or file type has no registry entry
- A brief or debrief references a file that doesn't exist
- A code symbol references a brief that doesn't exist
- **Barnacle check finds orphaned references** (deprecated content still active in playbooks)

The response is always the same: stop, fix the registers, confirm `just check` passes, then continue.

---

## The Barnacle Check

Barnacles are conventions without living justification — they misdirect agents and perpetuate bad practice. The Barnacle Removal System (BRS) identifies them; the barnacle check integrates detection into the integrity loop.

**What the check does:**
- Scans playbooks, docs, and briefs for orphaned references (services, endpoints, conventions that no longer exist)
- Flags temporal decay (instructions for deprecated systems older than a threshold)
- Reports findings in structured form (`decisions/drydock/pending.jsonl`)
- Fails `just check` if barnacle count exceeds threshold (configurable, default: warn-only)

**Where it fits in the process:**

```
just check
    ↓
  code check       → TS compiles, biome lints, DB usage clean
    ↓
  reg-sync         → indexes current, no drift
    ↓
  barnacle check   → no orphaned references in live docs
    ↓
  all green        → known-good state
```

The barnacle check runs AFTER the code check and BEFORE the final green signal. It is not a blocker — a barnacle finding generates a warning, not a hard failure — but it is visible. The agent sees it on every `just check`. Accumulated barnacles surface as a growing warning signal, prompting a scrub cycle.

**The scrub cycle:**

When barnacles accumulate, the BRS is run in full:
1. `scripts/barnacle-scrape.ts` identifies all barnacles → `decisions/drydock/pending.jsonl`
2. `scripts/barnacle-present.ts` presents findings via Gum/Charm table for human approval
3. Human approves or rejects each item
4. Approved barnacles moved to `decisions/drydock/` (gitignored, traceable)
5. Source files updated — orphaned references removed or updated
6. `just check` confirms clean state

The barnacle check is the early warning system. The scrub cycle is the remediation.

**Why integrate into `just check`:**

Barnacles are a form of index-rot in the conceptual layer. They accumulate silently — documentation that was correct at time of writing but no longer maps to reality. Without the check, barnacles are invisible until they cause confusion (an agent follows an outdated instruction, or a human is misled by a deprecated reference).

Running the barnacle check on `just check` makes it visible. Every session sees the barnacle count. The agent knows when to propose a scrub cycle.

**Design principle:** The check makes the problem visible. The human decides when to scrub. The agent does the work.

---

## Design Principles

1. **Every check is a full check.** Code AND registers. No partial checks.

2. **Fast is non-negotiable.** If checking everything is slow, people skip it. The code check must fund the register check.

3. **Drift is a stop signal.** Inconsistency is not background noise. It's the system telling you something is wrong.

4. **Agent maintains the registers.** Not humans manually. The agent does it as part of normal operation.

5. **Known-good state enables trust.** Clean registers mean you can cross-reference with confidence. Dirty registers mean you can't trust anything.

---

## The Broader Implication

The register system is a practical implementation of continuous self-testing. Traditional software testing checks code. This system checks the knowledge base — code, documents, and the relationship between them.

The agent doesn't just use the registers. It maintains them. It watches for drift. It fixes it. The system is not static — it's continuously self-correcting.

This is what a learning system looks like. Not one that accumulates documentation, but one that keeps its own state coherent.

---

*Tags: system-design, register-integrity, self-test, design-principle*