# Bug Diary (Member C)

Significant defects and verification-relevant discrepancies: symptom,
reproduction, classification, root cause, fix/status, and invariant gap. Only
entries supported by observed evidence are listed; nothing is inferred.

---

## BD-001 — Bedrock provider test fails under a stale global HTTP proxy

- **Symptom:** `tests/test_bedrock_provider.py::test_construction_when_extra_installed`
  fails in the offline baseline (`1 failed`).
- **Reproduction:**
  `.venv/bin/python -m pytest "tests/test_bedrock_provider.py::test_construction_when_extra_installed" -p no:cacheprovider`
  → exit 1, `ValidationError … Failed to connect to proxy URL: "http://127.0.0.1:7890"`.
  Re-run with `env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY …`
  → exit 0, 1 passed.
- **Classification:** environment / test-isolation (not an application regression).
- **Root cause:** `langchain_aws` is installed, so the test actually constructs a
  Bedrock client, which attempts credential/endpoint resolution through the
  ambient `http(s)_proxy`. No local proxy is listening.
- **Fix / status:** none applied (tests must not be changed during baseline).
  Recommended: run with proxy vars unset, or skip when a proxy is set. **Open** —
  needs A/E to record as a known exception for GOV-003.
- **Invariant gap:** none in the `SEL-TA-*` design; it is an upstream test's
  dependence on ambient env.

---

## BD-002 — As-of guard located in `resolve_run_context`, not the CLI entry

- **Symptom (found while writing TC-FR002-c):** a naive test at `cli/main.py`
  expected zero-run for `--portfolio` without `--portfolio-as-of`, but `run_analysis`
  was invoked (as-of `None` forwarded in `flags`).
- **Reproduction:** invoke the CLI with `--portfolio PATH` (no `--portfolio-as-of`)
  and observe that `cli/main.py` does not block; the typed `AS_OF_MISMATCH` is
  raised later by `cli/input_ui.resolve_run_context`.
- **Classification:** verification-boundary discrepancy (documentation/contract
  placement), **not** an application defect — enforcement exists in the designed
  guard.
- **Root cause:** contract §4 assigns the as-of rule to the input/consent service;
  the CLI entry only pre-checks the *both-flags* and *as-of-without-portfolio*
  combinations.
- **Fix / status:** test retargeted to `resolve_run_context` (TC-FR002-c now
  asserts `FLAG_CONFLICT` and `AS_OF_MISMATCH`). Test-plan change logged. **Closed.**
- **Invariant gap:** none; INV-09 is upheld by the shared guard.

---

## BD-003 — Bare `ConnectionError` is INTERNAL_ERROR, not MODEL_FAILURE

- **Symptom (found while writing TC-NFR001-d):** expectation that a raised
  `ConnectionError` maps to `MODEL_FAILURE` failed; code returns `INTERNAL_ERROR`.
- **Reproduction:**
  `classify_exception(ConnectionError("c"))` → `"INTERNAL_ERROR"`.
- **Classification:** test-expectation error (design is intentional).
- **Root cause:** `runapi/finalize.classify_exception` classifies by exception
  name/module; bare built-in connection errors are not provider-tagged, so they
  fall through to `INTERNAL_ERROR`. Real provider failures are `langchain`/`openai`/
  `anthropic`/`google` module exceptions (mapped to `MODEL_FAILURE`).
- **Fix / status:** test corrected to use a provider-module exception and
  `TimeoutError` for MODEL_FAILURE; added TC-NFR001-d2 pinning
  `ConnectionError → INTERNAL_ERROR`. **Closed** (no code change needed).
- **Invariant gap:** none; documents the intended classification boundary.
