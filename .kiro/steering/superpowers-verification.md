---
inclusion: auto
---

# Verification Before Completion

## The Iron Law

```
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
```

If you haven't run the verification command, you cannot claim it passes.

## The Gate

Before claiming any success or completion:

1. **IDENTIFY** — what command proves this claim?
2. **RUN** — execute the full command (fresh, complete)
3. **READ** — full output, check exit code, count failures
4. **VERIFY** — does output confirm the claim?
5. **ONLY THEN** — make the claim with evidence

## What Requires Verification

| Claim | Requires | Not Sufficient |
|-------|----------|----------------|
| Tests pass | Test command output showing 0 failures | Previous run, "should pass" |
| Linter clean | Linter output showing 0 errors | Partial check |
| Build succeeds | Build command exit 0 | "Looks correct" |
| Bug fixed | Reproduce original symptom: passes | "Code changed" |
| Requirements met | Line-by-line checklist against spec | "Tests pass" |

## Red Flags — STOP

- Using "should", "probably", "seems to"
- Expressing satisfaction before verification ("Done!", "Perfect!")
- About to commit without running tests
- Relying on partial verification
- Thinking "just this once"

## The Bottom Line

Run the command. Read the output. THEN claim the result. No shortcuts.
