# F5 Evidence Gate Scope Update (2026-06-07)

This note records the agreed scope change after the F5 preflight review:
the F5 validation path may use current persisted events, briefs, deliveries,
actions, backtests, refinements, and cost rows in the IIC SQLite DB instead of
forcing a fresh 72-hour soak. This keeps validation proportional to the system's
LLM/token cost while preserving an honest distinction between historical
evidence and live runtime soaking.

## Scope Decision

- `soak` mode remains the runtime gate and still requires `--since`.
- `evidence` mode validates existing DB rows and may be run without `--since`.
- G7 systemd restart checks are not DB evidence, so evidence mode marks G7 as
  not evaluated while allowing the evidence gate to pass if G1-G6, G8, and G9
  pass.
- Evidence mode must not be described as a 72-hour soak pass.

## Code Changes

- `Secretary.compose_deep_dive(..., deliver=True)` now fans out a deep-dive
  brief through configured delivery channels, making G3 measurable from DB
  delivery rows.
- `cli.deepdive.run_deepdive(..., deliver=True)` threads the delivery flag, and
  the user-facing `deepdive` command calls it with delivery enabled.
- `scripts/f5_exit_gate.py` now supports `--mode evidence`; the default remains
  `--mode soak`.

## Validation Commands

Focused regression tests:

```bash
python -m pytest \
  tests/secretary/test_service.py::test_compose_deep_dive_delivers_when_enabled \
  tests/cli/test_deepdive.py::test_run_deepdive_threads_deliver_flag \
  tests/scripts/test_f5_exit_gate.py::test_evidence_gate_uses_existing_db_rows_and_skips_runtime_g7 \
  -q
```

Evidence gate command:

```bash
python scripts/f5_exit_gate.py --mode evidence
```

Runtime soak command, if needed later:

```bash
python scripts/f5_exit_gate.py --mode soak --since "$SOAK_START"
```

## Operator Note

If evidence mode fails, fill only the missing evidence gap. Do not run a fresh
72-hour LLM-heavy soak unless the goal is specifically to validate runtime
stability over elapsed time.
