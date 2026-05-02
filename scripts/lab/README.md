# scripts/lab — Tier 0 Experiments

Rapid prototyping. Minimal type rigor. No promotion requirement.

## Rules

- **No strictness**: `strict: false`, `noImplicitAny: false`, `noUnusedLocals: false`
- **JS allowed**: `.js` files work alongside `.ts`
- **No emit**: code here never ships; it's for exploration
- **No review barrier**: commit freely, delete freely

## Promotion Pathway

When an experiment stabilizes:

```
scripts/lab/foo.ts          # Tier 0: wild west
    ↓ (add types, handle errors)
scripts/foo.ts              # Tier 1: internal tooling
    ↓ (enforce strict, add tests)
src/foo.ts                  # Tier 2: production code
```

See `playbooks/tsconfig-tiered-playbook.md` for full spec.
