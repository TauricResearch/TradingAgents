# Gap Analysis: Unified CLI vs. CLI Design Playbook

**Date:** 2026-05-07
**Scope:** `cli/trading/` implementation vs. `playbooks/cli-design-playbook.md`
**Result:** 11 gaps identified, 7 structural (citty migration), 4 cosmetic

---

## Gaps

### Gap 1: Not Using citty (Structural — Critical)

**Playbook:** Multi-subcommand CLIs **must** use `citty` with `defineCommand`.

**Current:** Custom `Bun.argv.slice(2)` parsing with a for-loop and `Record<string, function>` dispatch.

```typescript
// Current (non-compliant)
const args = Bun.argv.slice(2)
const command = args[0]
const COMMANDS: Record<string, (args: string[]) => void> = { plan: planCommand }
```

**Impact:**
- No auto-generated help
- No type-safe args
- No `--version`
- Manual error handling for missing args
- No lazy loading of subcommands

**Remediation:** Install citty, restructure with `defineCommand` + `runMain`.

---

### Gap 2: No `meta` Blocks (Structural — High)

**Playbook:** Every command must have `meta.name` and `meta.description`.

**Current:** Commands are bare functions. No metadata.

**Impact:** No auto-generated help. No `--help` per subcommand. Users must read source to discover flags.

**Remediation:** Wrap each command in `defineCommand({ meta: { name, description }, ... })`.

---

### Gap 3: Manual Arg Parsing (Structural — High)

**Playbook:** Use declarative `args` with `type`, `description`, `alias`, `required`.

**Current:** Each command manually iterates `argv` with string comparisons.

```typescript
// Current (non-compliant)
for (let i = 1; i < argv.length; i++) {
  if (argv[i] === "--platform" && argv[i + 1]) platform = argv[++i]
}
```

**Impact:**
- No validation (e.g., `--platform` without value silently ignored)
- No type inference
- No aliases (user must type full `--account`)
- No help text per flag

**Remediation:** Use citty `args` definitions with types, aliases, and descriptions.

---

### Gap 4: No Shared Arg Definitions (Structural — Medium)

**Playbook:** Export reusable arg definitions (e.g., `modelArg`) for consistency.

**Current:** `--platform`, `--account`, `--risk`, `--mode` are parsed independently in each command.

**Impact:** Duplication. Inconsistent aliases. Divergent defaults.

**Remediation:** Create `cli/trading/lib/args.ts` with shared definitions:
```typescript
export const platformArg = { type: "string", description: "Platform (ajbell, aviva, ig, nsandi)", alias: "p" }
export const accountArg = { type: "string", description: "Account balance in GBP", alias: "a" }
export const riskArg = { type: "string", description: "Risk per trade (e.g., 0.02 for 2%)", alias: "r" }
```

---

### Gap 5: Missing Exit Code 2 (Cosmetic — Low)

**Playbook:** Exit code `2` for missing required arguments.

**Current:** Only `0` (success) and `1` (all errors) used.

**Remediation:** citty handles this automatically when `required: true` is set on args.

---

### Gap 6: No Emoji Prefixes (Cosmetic — Medium)

**Playbook:** Use `❌ Error:`, `✅ Success:`, `⚠️ Warning:`, `ℹ️ Info:` prefixes.

**Current:** Plain text errors. Some warnings use `⚠️` in tables but not consistently.

```typescript
// Current
throw new Error(`Unknown platform: ${args.platform}`)

// Compliant
console.error(`❌ Error: Unknown platform "${args.platform}". Available: ajbell, aviva, ig, nsandi`)
```

**Remediation:** Add emoji prefixes to all console output. Standardize on playbook conventions.

---

### Gap 7: No `--version` Flag (Cosmetic — Low)

**Playbook:** `meta.version` provides `--version` automatically.

**Current:** No version support.

**Remediation:** Add `version: "0.1.0"` to main `defineCommand` meta.

---

### Gap 8: No Lazy Loading (Structural — Medium)

**Playbook:** Subcommands should be lazy-loaded.

**Current:** All commands imported eagerly in `main.ts`.

```typescript
// Current (non-compliant)
import { planCommand } from "./commands/plan.ts"
const COMMANDS = { plan: planCommand }
```

**Remediation:** Use dynamic imports in subcommand definitions:
```typescript
subCommands: {
  plan: () => import("./commands/plan.ts").then(m => m.planCommand),
}
```

---

### Gap 9: No Actionable Error Messages (Cosmetic — Medium)

**Playbook:** Error messages should show available options.

**Current:**
```typescript
throw new Error(`Unknown platform: ${args.platform}`)
```

**Compliant:**
```typescript
console.error(`❌ Error: Unknown platform "${args.platform}". Available: ajbell, aviva, ig, nsandi`)
```

**Remediation:** Update all error throws to include context + available values.

---

### Gap 10: No Test Coverage for Help/Validation (Cosmetic — Low)

**Playbook:** Test `--help`, missing args, validation, exit codes.

**Current:** No tests.

**Remediation:** Add `tests/cli/` with tests for:
- `trading --help` renders all commands
- `trading plan --help` shows all flags
- `trading plan` (no ticker) exits with code 2
- `trading plan AAPL --platform invalid` exits with code 1

---

### Gap 11: No `package.json` bin Entry (Structural — Low)

**Playbook:** CLI should be installable globally via `bin` entry.

**Current:** `cli/trading/main.ts` exists but no `package.json` entry.

**Remediation:** Add to root `package.json`:
```json
"bin": {
  "trading": "./cli/trading/main.ts"
}
```

---

## Remediation Priority

| Priority | Gap | Effort | Impact |
|----------|-----|--------|--------|
| **P0** | 1 — Use citty | 1d | Critical — framework migration |
| **P0** | 2 — Add meta blocks | Included in #1 | High — auto-help |
| **P0** | 3 — Declarative args | Included in #1 | High — type safety |
| **P1** | 4 — Shared arg defs | 0.5d | Medium — DRY |
| **P1** | 8 — Lazy loading | 0.5d | Medium — startup perf |
| **P1** | 6 — Emoji prefixes | 0.25d | Medium — UX |
| **P1** | 9 — Actionable errors | 0.25d | Medium — UX |
| **P2** | 5 — Exit code 2 | Included in #1 | Low — citty handles |
| **P2** | 7 — Version flag | Included in #1 | Low — one line |
| **P2** | 10 — Test coverage | 0.5d | Low — safety net |
| **P2** | 11 — bin entry | 0.1d | Low — distribution |

---

## What We Did Right

| Area | Status |
|------|--------|
| Platform taxonomy (AJBell=SIPP, etc.) | ✅ Correct per user |
| Spread betting formula | ✅ Mathematically sound |
| Platform validation (spreadbet=IG-only) | ✅ Hard error |
| Pretty table output | ✅ Good UX |
| Pure calculation functions | ✅ Reusable, testable |
| Bracket order formatting | ✅ Clear and actionable |

---

## Recommended Path

1. **Install citty:** `bun add citty`
2. **Restructure main.ts:** `defineCommand({ meta, subCommands })` + `runMain`
3. **Restructure plan.ts:** `defineCommand({ meta, args, run })`
4. **Extract shared args:** `cli/trading/lib/args.ts`
5. **Add emoji + actionable errors:** Update all `throw` and `console` statements
6. **Add tests:** `tests/cli/trading.test.ts`
7. **Add bin entry:** `package.json`

Total estimate: **2 days** for full compliance.
