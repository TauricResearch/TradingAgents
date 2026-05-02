# Playbook: Tiered TypeScript Configuration

**PHI-14 (Architectural Specialization) applied to TS rigor.**

---

## Philosophy

Not all TypeScript needs the same rigor. Different tiers have different:

| Tier | Location | Type Strictness | Review | Risk |
|------|----------|-----------------|--------|------|
| 0 | `@scripts/lab/` | Minimal | None | High |
| 1 | `scripts/` | Standard | Required | Medium |
| 2 | `src/` | Full | Required | Low |

**The right rigor for the right tier.**

---

## Tiered tsconfig Files

### Tier 2: `tsconfig.json` (Production)

Full strict mode for `src/`:

```json
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitReturns": true,
    "noFallthroughCasesInSwitch": true,
    "strictNullChecks": true,
    "strictFunctionTypes": true,
    "strictBindCallApply": true,
    "strictPropertyInitialization": true,
    "noImplicitAny": true,
    "noImplicitThis": true,
    "useUnknownInCatchVariables": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true
  }
}
```

**When to use:** `src/**/*.ts` — production code that ships.

---

### Tier 1: `tsconfig.scripts.json` (Stable Scripts)

Standard mode for `scripts/`:

```json
{
  "compilerOptions": {
    "strict": false,
    "noImplicitAny": false,
    "strictNullChecks": false,
    "noUncheckedIndexedAccess": false,
    "noUnusedLocals": false,
    "noUnusedParameters": false,
    "allowJs": true,
    "skipLibCheck": true
  }
}
```

**When to use:** `scripts/**/*.ts` — internal tooling, build scripts.

---

### Tier 0: `@scripts/lab/` (Experiments)

Minimal or no TS config. Experiments may be pure JS/Shell.

```json
{
  "compilerOptions": {
    "strict": false,
    "noEmit": true,
    "allowJs": true,
    "checkJs": false
  }
}
```

**When to use:** `@scripts/lab/**/*.ts` — rapid prototyping.

---

## Usage

```bash
# Type-check production (Tier 2)
npx tsc --project tsconfig.json

# Type-check scripts (Tier 1)
npx tsc --project tsconfig.scripts.json

# All tiers
npx tsc --project tsconfig.json --project tsconfig.scripts.json
```

---

## Strictness Levels

| Setting | Tier 2 | Tier 1 | Tier 0 |
|---------|--------|--------|--------|
| `strict` | ✓ | ✗ | ✗ |
| `noImplicitAny` | ✓ | ✗ | ✗ |
| `strictNullChecks` | ✓ | ✗ | ✗ |
| `noUncheckedIndexedAccess` | ✓ | ✗ | ✗ |
| `noUnusedLocals` | ✓ | ✗ | ✗ |
| `noUnusedParameters` | ✓ | ✗ | ✗ |
| `allowJs` | ✗ | ✓ | ✓ |
| `skipLibCheck` | ✓ | ✓ | ✓ |

---

## Promotion Pathway

```
@scripts/lab/experiment.ts    # Tier 0: Experiment
        ↓
scripts/stable.ts             # Tier 1: Promote, add types
        ↓
src/stable.ts                 # Tier 2: Full rigor
```

When promoting:
1. Add type annotations
2. Enable strict checks
3. Run `tsc --strict` before commit
4. Add tests

---

## Anti-Patterns

| Anti-Pattern | Problem | Fix |
|--------------|---------|-----|
| `any` in Tier 2 | Defeats type safety | Use `unknown` + narrowing |
| Tier 2 config for scripts | Over-rigor | Use `tsconfig.scripts.json` |
| Tier 1 config for experiments | Over-rigor | Use `@scripts/lab/` |
| Skipping promotion | Technical debt | Promote when stable |

---

## Gamma-Loop Integration

During tidy phase:
- What experiments in `@scripts/lab/` are stable enough to promote?
- What scripts need stricter types?
- Archive abandoned experiments

---

## See Also

- `AGENTS.md` — Experimental tiers
- `scripts/lab/README.md` — Lab rules
- `playbooks/justfile-design-playbook.md` — Simplicity rule
