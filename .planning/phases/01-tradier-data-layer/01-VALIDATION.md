---
phase: 1
slug: tradier-data-layer
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-29
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | none — Wave 0 installs |
| **Quick run command** | `python -m pytest tests/test_tradier.py -x -q` |
| **Full suite command** | `python -m pytest tests/ -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_tradier.py -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | DATA-01 | unit | `python -m pytest tests/test_tradier.py -k chain -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | DATA-02 | unit | `python -m pytest tests/test_tradier.py -k expirations -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | DATA-03 | unit | `python -m pytest tests/test_tradier.py -k greeks -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | DATA-04 | unit | `python -m pytest tests/test_tradier.py -k iv -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | DATA-05 | unit | `python -m pytest tests/test_tradier.py -k dte -q` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | DATA-08 | integration | `python -m pytest tests/test_tradier.py -k vendor -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_tradier.py` — stubs for DATA-01 through DATA-05 and DATA-08
- [ ] `tests/conftest.py` — shared fixtures (mock Tradier responses)
- [ ] pytest install — if not already present

*If none: "Existing infrastructure covers all phase requirements."*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Production Greeks accuracy | DATA-03 | Sandbox returns no Greeks; production API key required | Call chain for AAPL, verify delta/gamma/theta/vega/rho are non-null floats |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
