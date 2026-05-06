# PR #8 Review Checklist

Generated from Qodo + CodeRabbit review comments.
Source: `debriefs/reviews/pr-8.md`

---

## 🔴 Issue 1: Python tests in `tests/` (Rule violation)

**Severity:** Rule violation (AGENTS.md compliance)
**What:** Added pytest tests in `tests/test_server_lib.py` — outside the designated Python boundaries.
**Where:** `tests/test_server_lib.py[155-170]`

- [ ] **Action:** Either:
  - Move tests to Bun/TypeScript test suite, OR
  - Relocate to explicitly allowed Python area (if intended), OR
  - Document exception in AGENTS.md

---

## 🔴 Issue 2: SQLite REAL values not parsed (Correctness bug)

**Severity:** Bug — incorrect calculations
**What:** `intel-compute.ts` does arithmetic on SQLite REAL columns (`avg_cost`, `balance`, `entry_price`, `stake_per_point`) without `parseFloat()`. SQLite REALs may return as strings.
**Where:**
- `server/lib/intel-compute.ts[78-85]` — position cost/value math
- `server/lib/intel-compute.ts[111-113]` — spread bet notional
- `server/lib/intel-compute.ts[165-169]` — account aggregation

- [ ] **Action:** Add `parseFloat()` wrapper before all numeric operations on REAL columns.
- [ ] **Verify:** Check `server/lib/schema.sql` REAL columns match the fields being parsed.

---

## 🔴 Issue 3: Misresolved `resultsDir` path (Correctness bug)

**Severity:** Bug — analyses filesystem routes will look in wrong directory
**What:** `cfg.paths.resultsDir` duplicates path segments. `settings.json` defaults include `.tradingagents/logs` but `settings.ts` `taRoot()` appends `.tradingagents` to HOME, so `resolvePath()` joins them into `~/.tradingagents/.tradingagents/logs`.
**Where:**
- `server/lib/settings.ts[52-59]` — `taRoot()` function
- `server/lib/settings.ts[74-93]` — path resolution
- `server/lib/settings.json[4-13]` — defaults
- `server/routes/analyses-common.ts[6-9]` — `resultsDir()`

- [ ] **Action:** Fix path resolution — either:
  - Base `taRoot()` on `HOME` (not `$HOME/.tradingagents`) and keep defaults as `.tradingagents/logs`, OR
  - Base `taRoot()` on `$HOME/.tradingagents` and change defaults to `logs`, `positions`, etc.
- [ ] **Action:** Add smoke assertion that `cfg.paths.resultsDir` resolves correctly.

---

## 🔴 Issue 4: FreshnessBadge UTC day mismatch (Correctness bug)

**Severity:** Bug — off-by-one day in freshness indicator
**What:** Uses `now.getFullYear()` / `getMonth()` / `getDate()` (local) inside `Date.UTC()`, reintroducing timezone dependence. Also no validation of `dateStr` format — malformed input yields NaN.
**Where:** `server/views/holdings.tsx[29-57]`

- [ ] **Action:** Use UTC getters: `now.getUTCFullYear()`, `getUTCMonth()`, `getUTCDate()`
- [ ] **Action:** Validate `dateStr` with `^\d{4}-\d{2}-\d{2}$` regex; return neutral badge (`—`) if invalid

---

## 📝 Notes

- All 4 issues are from automated review (Qodo). No human reviews yet.
- Issue 1 may be a false positive — `tests/` is explicitly for Python smoke tests per project convention.
- Issues 2 and 3 are data/correctness bugs that should be fixed before merge.
- Issue 4 is a refinement of an already-attempted fix (td-18e84e).
