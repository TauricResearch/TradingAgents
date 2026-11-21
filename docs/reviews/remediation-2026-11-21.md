# Integration review remediation 2026 11 21

This record follows Member B's `project-review-2026-11-18.md`. Changes are local and uncommitted. They are developer remediation and regression evidence, not Member C's independent acceptance or an application wide correctness guarantee. Existing F1/F2 work was preserved and extended.

## Changes and remaining acceptance

- **F1:** safe single component run IDs, resolved path containment, staging creation ownership and inode identity checks before cleanup. Collision, concurrent reused IDs, traversal, absolute paths, symlink escape and replaced staging ownership are covered. The staged atomic publication architecture is retained.
- **F2:** provider prefixed assignments, quoted/multiline values, Bearer/Basic forms and actual environment configured secret values are redacted. Regression tests cover text, exceptions, nested values, persisted report/HTML/manifest/state/message outputs and real lifecycle event output. Synthetic canaries only; this does not certify all conceivable secret encodings.
- **F3:** scorer validates formal evidence, completed result fields, artifact hashes, report/manifest identity, fixed configuration, revision and report correspondence. Human score cells bind to case/run/trial/item, require report citations and reviewer identity, and reject missing, duplicate, unrelated, unknown, boolean or N/A values. Critical safety items cannot be hidden by omitting a caller flag. Captured prompt digests and per-call marker observations support challenge exposure; a true flag alone is insufficient.
- **F4:** all recorded formal starts remain in overall completion accounting. A reviewed, predeclared ten-slot cohort determines the formal population; failed slots are not replaced. Retries are reported separately. Both overall completion and cohort completion must satisfy the gate; semantic scores are separate from completion. The harness accepts planned IDs and refuses to reuse a started formal slot. External approval retention is necessary to audit chronology.
- **F5:** structural tests scan the actual repository, assert nonempty source sets and detect relevant prompt imports, `from rich import prompt`, typer and direct input. Negative fixtures prove forbidden patterns are found.
- **F6:** number parsing and file loading have separate exception handling. Selecting invalid JSON now exposes its file diagnostic and the intended retry/cancel behavior.
- **F7:** the existing run scoped config now supplies actual cap/threshold values to every shared prompt guard. Analyst guards measure rendered templates as well as history. Instrument and portfolio instructions are explicitly protected through compaction; system/developer messages and provider content blocks preserve their semantics or fail closed when the protected content cannot fit. These are character/4 estimates, not exact provider billing or total-run token budgets. Graph run settings and manifests record the applied settings. Prompt source hashing includes portfolio, structured invocation and analyst turn helpers.
- **F8:** portable relative evidence paths and artifact hashes are emitted; `package_gov004.py` exports referenced evidence with an integrity inventory and refuses detected credential content. Relocation testing removes the original evidence directory before rescoring the exported package. Shared ignore rules exclude private live outputs. Historical PASS statements have prominent PENDING audit notices. **The original historical reports/manifests/scores are absent, so F8 historical evidence acceptance remains open. No old scores, approval or timestamps were invented.**
- **F9:** absent holdings explicitly prohibit implying ownership; a supplied flat or zero target position explicitly prohibits trimming or retaining nonexistent exposure. Other-ticker-only holdings remain distinct from target holdings, and unknown cash is not inferred. Portfolio Manager and Research Manager rating legends are conditional; Trader treats bearish actions as avoid-entry guidance when no long position is supplied. Supplied context overrides ownership assumptions in upstream plans. The five tier research vocabulary and limited Q1–Q4 authority are retained. Independent-style developer prompt captures cover absent, flat, other ticker, zero quantity, long and short snapshots under nondefault compaction. **Actual narrative semantic acceptance remains open until live output can be obtained and independently reviewed.**

## Validation

Environment: existing `/opt/anaconda3/bin/python`, Python 3.14. Pytest plugin autoload was disabled to avoid unrelated globally installed plugins. Built-in subtests still executed. Sandboxed baseline failures from loopback socket binding and a repository cache write disappeared when the same suite ran with the necessary filesystem/socket permissions; no assertions were disabled.

Before this remediation: **1518 passed, 2 skipped, 1 deselected, 24 warnings, 100 subtests passed**.

After remediation: **1552 passed, 2 skipped, 1 deselected, 24 warnings, 100 subtests passed** (12.05 seconds in the final run). This adds 34 tests compared with the local starting baseline. Skips remain opt-in live replay and optional Bedrock support; the existing integration selection is unchanged.

Commands from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/anaconda3/bin/python -m pytest -q -p no:cacheprovider --tb=short
/opt/anaconda3/bin/python -m ruff check --no-cache . --output-format concise
git diff --check
python tests/member_c_verification/live/score_gov004.py
```

Ruff: **All checks passed**. Diff whitespace check: passed. The default scorer reports zero evidence and **PENDING**, exit 2, as required. It does not claim formal semantic acceptance.

Targeted regressions live in `tests/member_d_verification/`; original independent exit-code fixtures were upgraded to contain a valid frozen cohort, full manifests, hashes, captured input metadata and applicable scores. Invalid evidence was not allowed merely to keep the old PASS fixture green. Original application test assertions were preserved.

## Authorized real model diagnostics

`tests/member_d_verification/live_f9_probe.py --live` attempted the configured school `openai_compatible` model `CS5351/DeepSeek-V4-Flash` with five synthetic cases: absent portfolio, explicit empty, other ticker only, held target with unknown cash, and explicit empty with known cash. It supplied a conflicting upstream draft to exercise ownership correction. No real account data or market tools were used and no trades were executed.

All **5 started cases remain INCOMPLETE** because provider connection failed. A separate minimal connection diagnostic traced the cause to DNS resolution (`gaierror`), outside the sandbox as well. No usable live narrative was obtained; no semantic pass or token saving is claimed. Failed attempts remain in the private `.local-review/f9-diagnostic-20261120T201810Z.json` record (UTC timestamp, 21 November in Hong Kong). Endpoints and credentials are not reproduced here. Stop repeated paid replay until connectivity is restored.

## Handoff

1. C independently reviews the repaired behavior, new scorer and developer tests. A/C ratify the explicit critical-item policy, frozen cohort protocol and any formal provider configuration change; saved school diagnostics do not silently change the formal fixed provider.
2. C/E supply and retain the original historical sanitized evidence for F8, or explicitly withdraw/requalify the historical acceptance claim.
3. Restore school API DNS access and rerun the opt-in F9 probe, then perform actual narrative adjudication. Fresh diagnostics must remain separate from the approved formal cohort.
4. Use `docs/verification/gov004-evidence-package.md` to package and verify reviewed evidence from a fresh checkout. CI/governance installation and final submission assembly are separate work.
