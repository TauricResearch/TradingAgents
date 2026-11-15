# R4 Option Evaluation and Verification

This table covers R4 only. See [ADR-0001](adr/0001-r4-cost-policy.md) for the decision. Detailed run results are recorded in `R4测试记录.md` in the parent directory; local live logs are under `pre_evidence/` there. Neither is automatically included in the Git repository.

## Candidate Approaches

| Approach | Cost awareness | Effect on existing log | Verification and effort | Decision |
| --- | --- | --- | --- | --- |
| Keep recording gross price return only | None | None | Simplest, but does not meet R4. | Rejected |
| Fixed bps with a minimum-commission rate floor | Provides a bounded net-return estimate | Reuses existing fields; legacy entries need separate interpretation | Fixed prices make the formula testable; changes stay in settlement and reflection. | Selected |
| Add orders, quantities, multicurrency fees, and a broker ledger | Closest to actual fills | Requires new fields and migration | No real order inputs exist; scope and validation cost exceed R4. | Defer to a later requirement |

## Completed Verification

| Scope | Data and external dependencies | Observed result | Limit |
| --- | --- | --- | --- |
| Cost formula and minimum commission | Local fixed values; no network | A 5% gross return with 10 bps per side yields a 4.790105% net return; the minimum-commission example gives 0.25% per side. | Tests a simplified formula, not actual broker fees. |
| R4 offline tests | Fixed NVDA/SPY prices and a fake LLM | 26 tests passed, covering defaults, switch, incomplete window, settlement, reflection, and failures. | Does not establish Yahoo or course model availability. |
| Full offline regression | Project tests isolate external network access | 1285 passed, 4 skipped, 2 deselected; `ruff check .` passed. | Online `integration` tests are deselected by default. |
| Course model reflection | Simulated BABA/SPY prices and the real course LLM | One integration test passed and stored a nonempty reflection. | Prices remain simulated. |
| Yahoo price settlement | Real BABA/SPY historical prices and the course LLM | The fixed 2026-10-01 decision settled; net return was about -1.8% and net alpha about -3.1%. | Decision text was a test assumption; no trade was executed. |
| Full CLI smoke | Yahoo prices, course LLM, and BABA market analyst | Fixed-date and `--latest` runs both reported `R4 CLI LIVE SMOKE: PASS`; the latest complete session in that run was 2026-11-13. | Confirms the CLI, data, model, settlement, and log worked together in those runs. |

In the latest-session run, the prior decision was dated 2026-10-30 and resolved on 2026-11-06, with about +11.4% net return and +14.1% net alpha. The new analysis remained `pending`. Some structured model outputs fell back to plain text without stopping the workflow. These results do not assess advice quality or predict results on later dates.
