# Epic/Brief: TradingAgents Hardening and Cleanup

**Date:** 2026-05-15
**Status:** Open

---

## Task: Harden and tidy the TradingAgents fork

**Objective:** Improve the repo’s readiness by closing the most obvious product, security, and maintainability gaps without changing the core trading engine.

## What

- [ ] Add an authentication or access-control plan for the dashboard, including a documented default stance for local/dev usage and a path for production deployment.
- [ ] Replace any stubbed or incomplete dashboard routes with working implementations or explicit “not implemented” responses that are surfaced consistently in the UI.
- [ ] Reduce fork churn by identifying and removing or archiving clearly temporary artifacts that are no longer needed for normal development.
- [ ] Improve consistency across the TypeScript/Python boundary by documenting the supported subprocess bridge flow and ensuring all dashboard-to-Python communication follows the agreed JSON-lines contract.
- [ ] Make the operational workflow easier to follow by ensuring the primary setup, run, test, and seed commands are discoverable from the main docs and match the actual repo behavior.

## How to Verify

- [ ] Run `just check` and confirm it passes without new lint or type errors.
- [ ] Start the dashboard locally and verify the main navigation, analysis flow, and error handling behave consistently.
- [ ] Confirm any previously stubbed routes either work end-to-end or show an intentional, documented fallback state.
- [ ] Review the repository root and key docs to confirm temporary or transitional files are either removed, archived, or clearly justified.
- [ ] Manually trace one dashboard analysis request from UI to subprocess bridge and confirm the event format stays JSON-lines only.
- [ ] Edge case: run in `TEST_MODE=1` and verify the isolated environment still works independently of dev state.

## Technical Notes

- Keep the Python trading core untouched unless a fix absolutely requires upstream-style changes.
- Prefer TypeScript/Bun for dashboard and support work.
- If a design decision requires choosing between multiple viable approaches, capture it in an ADR.
- If a cleanup step risks losing useful history, archive rather than delete.
- This brief intentionally targets repo health and readiness rather than feature expansion.

---

## Done

When all `[ ]` items are checked and verified.