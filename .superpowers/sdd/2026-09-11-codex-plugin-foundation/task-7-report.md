# Task 7 verification report

Date: 2026-09-11

## Scope delivered

- Added `scripts/smoke_plugin_protocol.py`, a standalone installed-package smoke that runs from a temporary cwd, verifies `python -I` imports from installed site-packages, initializes the installed `tradingagents-mcp` executable through the SDK, lists tools, and calls `get_capabilities` without LLM keys.
- Added a JSON-RPC stdout regression: it sends `initialize` (protocol `2025-11-25`), `notifications/initialized`, and `tools/list`; parses every stdout line as JSON; and requires JSON-RPC 2.0 responses with IDs 1 and 2. Stderr remains separate.
- Added the non-editable four-version plugin CI job and the isolated no-MCP assertion to the base-install job. Base test and lint jobs are unchanged.
- Added runtime setup/limitations documentation. The approved specification's staged-acceptance paragraph is unchanged.

## Environment

| Item | Actual value |
| --- | --- |
| Worktree | `/tmp/tradingagents-plugin-foundation` on `codex/plugin-foundation` |
| Host | `Darwin 25.5.0 arm64` |
| Development interpreter | Python 3.12.13 |
| Additional clean-smoke interpreter | Python 3.13.14 |
| MCP SDK | `mcp==1.26.0` |
| Test/lint tooling | pytest 9.1.1; Ruff 0.16.7; pip 26.1 |
| Shell caveat | `python` was initially unavailable until a dedicated venv was activated. |

## Commands and results

### Base install (fresh, non-editable, Python 3.12.13)

```bash
/opt/homebrew/bin/python3.12 -m venv /tmp/tradingagents-task7-base.XJg5Th/venv
/tmp/tradingagents-task7-base.XJg5Th/venv/bin/python -m pip install .
/tmp/tradingagents-task7-base.XJg5Th/venv/bin/python -I -c "import importlib.util; import tradingagents, cli.main; assert importlib.util.find_spec('mcp') is None"
```

Exit status: 0. The isolated base import succeeded and `mcp` was absent.

### Plugin clean installs (fresh, non-editable)

Python 3.12.13:

```bash
/tmp/tradingagents-task7-clean.IJJ2KY/venv/bin/python -m pip install ".[plugin]"
/tmp/tradingagents-task7-clean.IJJ2KY/venv/bin/python -m pip check
/tmp/tradingagents-task7-clean.IJJ2KY/venv/bin/python scripts/smoke_plugin_protocol.py
```

Exit status: 0. `pip check` output: `No broken requirements found.`

Python 3.13.14:

```bash
.venv/bin/python -m venv /tmp/tradingagents-task7-py313.5vILGa/venv
/tmp/tradingagents-task7-py313.5vILGa/venv/bin/python -m pip install ".[plugin]"
/tmp/tradingagents-task7-py313.5vILGa/venv/bin/python -m pip check
/tmp/tradingagents-task7-py313.5vILGa/venv/bin/python scripts/smoke_plugin_protocol.py
```

Exit status: 0. `pip check` output: `No broken requirements found.` The smoke's isolated import assertion passed in both environments. Each run emitted `pydantic_settings`'s `IncompleteFieldDefinitionWarning` on stderr for its `lifespan` field; no protocol stdout was merged with stderr or treated as successful protocol output.

### Editable development gate (Python 3.12.13)

```bash
python -m pip install -e ".[dev,plugin]"
python -m pytest tests/test_plugin_runtime.py tests/test_plugin_capabilities.py \
  tests/test_shared_analyst_prompts.py tests/test_shared_synthesis.py -q
ruff check .
python -m pip wheel . --no-deps -w /tmp/tradingagents-foundation-dist
git diff --check
```

Results:

- Editable install: exit 0.
- Focused tests: `57 passed in 1.05s`.
- `ruff check .`: `All checks passed!` (exit 0).
- Wheel build: exit 0; built `tradingagents-0.4.0-py3-none-any.whl`.
- `git diff --check`: exit 0.

### Full suite

```bash
python -m pytest -q
```

Exit status: 1: `9 failed, 724 passed, 2 skipped, 18 warnings, 73 subtests passed in 2.67s`.
All nine failures are `tests/test_i18n_coverage.py::test_report_agent_applies_language_instruction`. That test searches source text for `get_language_instruction()` in Task 3–6 role modules. Those commits replaced direct global reads with explicit `output_language=language` passed to shared builders. `git log` attributes the mismatch to prior `dd87cc6`/`7cd59d0` extractions, not Task 7. This task leaves that unrelated legacy source-text test unchanged.

## PRD acceptance record

| Story | Evidence | Status |
| --- | --- | --- |
| US-001 | Base clean install without MCP; non-editable plugin install outside the checkout; SDK initialize/list/call smoke; manual JSON-RPC stdout test; existing unwritable-state-root test in the focused run. | Passed locally on Python 3.12 and 3.13. |
| US-002 | SDK smoke asserts only `get_capabilities` is registered and FRED is credential-absent; existing capability tests ran in the focused 57-test set. | Passed locally. |
| US-003 | `tests/test_shared_analyst_prompts.py` ran in the focused set. | Extraction checks passed; real plugin consumption remains open for US-009. |
| US-004 | `tests/test_shared_synthesis.py` ran in the focused set. | Extraction checks passed; no full-product completion claim. |

## CI matrix and concerns

The new GitHub Actions `plugin` job retains the required Linux matrix: 3.10, 3.11, 3.12, and 3.13. It was not dispatched from this local worktree, so no CI job is claimed passed.

| Requested runner | Local result |
| --- | --- |
| Python 3.10 | Unavailable: `python3.10` command not found. |
| Python 3.11 | Unavailable: `python3.11` command not found. |
| Python 3.12 | Clean non-editable install, `pip check`, and protocol smoke passed. |
| Python 3.13 | Clean non-editable install, `pip check`, and protocol smoke passed. |
| GitHub Ubuntu matrix | Unavailable locally; must pass in CI before treating matrix compatibility as complete. |

Open concerns: the pre-existing full-suite i18n source-text mismatch must be reconciled outside Task 7; and the third-party stderr warning noted above is non-protocol noise worth tracking if clean stderr becomes a future requirement. Host manifest/activation and a real plugin workflow are still later US-018/US-005+ work.

## Fix round 1

### Findings addressed

1. `tests/test_plugin_runtime.py` no longer calls blocking `readline()`, `readlines()`, or an
   unbounded post-timeout `wait()`. It sets both pipes nonblocking, reads with `selectors` and a
   shared 30-second deadline, retains partial bytes until newline boundaries, parses every
   captured stdout line, and bounds terminate/kill/wait/drain cleanup by that same deadline.
2. `tests/test_i18n_coverage.py` now checks each listed report builder for the explicit
   `get_language_instruction(output_language)` contract. It does not revert explicit language
   propagation; the existing builder behavior tests remain in the covering suite.

### Fix-round commands and actual outputs

```bash
python -m pytest tests/test_plugin_runtime.py::test_stdio_protocol_stdout_is_json_rpc \
  tests/test_i18n_coverage.py -q
```

Output: `15 passed in 0.83s`.

```bash
python -m pytest tests/test_plugin_runtime.py tests/test_plugin_capabilities.py \
  tests/test_shared_analyst_prompts.py tests/test_shared_synthesis.py \
  tests/test_i18n_coverage.py -q
```

Output: `71 passed in 0.97s`.

```bash
python -m pytest -q
ruff check .
python -m pip wheel . --no-deps -w /tmp/tradingagents-foundation-dist
git diff --check
/tmp/tradingagents-task7-clean.IJJ2KY/venv/bin/python scripts/smoke_plugin_protocol.py
```

Outputs/statuses: `733 passed, 2 skipped, 18 warnings, 73 subtests passed in 2.37s` (pytest
exit 0); `All checks passed!` (Ruff exit 0); wheel `tradingagents-0.4.0-py3-none-any.whl` built
(exit 0); diff check exit 0; non-editable Python 3.12.13 protocol smoke exit 0. The smoke again
emitted only the known `pydantic_settings` `IncompleteFieldDefinitionWarning` on stderr.

The unavailable Python 3.10/3.11 interpreters and GitHub Ubuntu matrix remain unavailable
locally and are not claimed passed.
