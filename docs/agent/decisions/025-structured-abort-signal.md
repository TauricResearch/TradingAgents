# ADR 025: Structured Abort Signal Replaces `[CRITICAL ABORT]` String Prefix

**Date**: 2026-04-25
**Status**: Proposed
**Tags**: [graph, routing, decision-integrity, refactor]
**Related files**:
- `tradingagents/agents/utils/critical_abort.py`
- `tradingagents/graph/setup.py`
- `tradingagents/graph/conditional_logic.py`
- `tradingagents/agents/utils/agent_states.py`

## Context

The trading graph routes around upstream failures via a string-prefix
marker: any analyst report that begins with `[CRITICAL ABORT]` causes
the conditional router to redirect to the **Critical Abort Terminal**
node. Detection is implemented in
`critical_abort.py::report_has_critical_abort` as a substring check
against report text fields.

Two structural problems:

1. **False-positive risk.** Any analyst content that legitimately
   contains the literal string `[CRITICAL ABORT]` (e.g., a quoted
   news headline, a fact-check transcript, a debug excerpt) would
   route the entire pipeline to the terminal node. There is currently
   no escaping mechanism.
2. **No metadata.** The marker is a flag, not a payload. A consumer
   downstream of the abort terminal cannot programmatically
   distinguish "news prefetch failed" from "instrument key invalid"
   from "fundamentals empty TTM" without parsing the prose body.
3. **Tight coupling to text fields.** The conditional must scan
   every report field (`market_report`, `sentiment_report`, etc.)
   to find the marker. Adding a new analyst means updating
   `state_has_critical_abort` to scan its field too.

Per ADR 023 the rest of the decision-integrity story is moving
toward explicit structured signals. The abort mechanism should match.

## Decision

Replace the string-prefix marker with a structured field on
`AgentState`:

```python
# tradingagents/agents/utils/agent_states.py
class AbortSignal(TypedDict):
    source: str            # node name that raised it, e.g. "news_analyst"
    reason: str            # short machine-readable code
    detail: str            # human-readable diagnosis
    raised_at: str         # ISO timestamp
    recoverable: bool      # whether a partial rerun could fix it

class AgentState(MessagesState):
    ...
    abort_signal: AbortSignal | None
    ...
```

### Routing change

`should_continue_to_*` conditionals after each analyst become a single
predicate:

```python
def _route_or_abort(next_node: str):
    def cond(state: AgentState) -> str:
        if state.get("abort_signal"):
            return CRITICAL_ABORT_NODE
        return next_node
    return cond
```

The conditional no longer scans report text fields — `O(1)` instead
of `O(num_analysts × report_length)`.

### Reason taxonomy (initial)

| Reason code | Source nodes | Recoverable? |
|---|---|---|
| `instrument_key_invalid` | Instrument Preflight | no |
| `news_prefetch_failed` | News Analyst | yes (rerun analyst) |
| `news_evidence_missing` | News Fact Checker | yes |
| `news_schema_invalid` | News Analyst | yes |
| `fundamentals_empty_ttm` | Fundamentals Analyst | yes |
| `social_prefetch_failed` | Social Analyst | yes |
| `market_data_unavailable` | Market Analyst | yes |

Adding a new reason requires extending the `Literal` type so the
checker enforces exhaustiveness.

### Migration of `critical_abort.py`

```python
# Before
CRITICAL_ABORT_PREFIX = "[CRITICAL ABORT]"

def report_has_critical_abort(text: str) -> bool: ...
def state_has_critical_abort(state) -> bool: ...
def extract_abort_report(state) -> str: ...

# After
def raise_abort(state, source, reason, detail, recoverable=True) -> dict:
    """Build the partial state update that signals an abort."""
    return {"abort_signal": {
        "source": source, "reason": reason, "detail": detail,
        "raised_at": datetime.now(UTC).isoformat(),
        "recoverable": recoverable,
    }}

def has_abort(state) -> bool:
    return state.get("abort_signal") is not None
```

Analysts that today write `[CRITICAL ABORT] <body>` into a report
field instead return `raise_abort(state, source=..., reason=...)`
merged with whatever partial state they were going to write.

### Critical Abort Terminal

`critical_abort_terminal.py` now reads `state["abort_signal"]`
instead of scanning report fields. It composes
`final_trade_decision` from the structured payload, sets
`terminal_action`, `analysis_status="aborted"`, and writes the abort
signal to disk for forensic inspection.

## Migration plan

1. Add `abort_signal` to `AgentState` (default `None`). Keep
   `critical_abort.py`'s old API as deprecation shims that
   internally set the structured field.
2. Update each analyst factory to call `raise_abort(...)` instead of
   prefixing report text. Remove the old prefix from analyst
   prompts.
3. Update conditional routers to use `has_abort(state)`.
4. Update the terminal node to read the structured field.
5. Remove the deprecated string-prefix shims and constant. Update
   ADR 023's references to `[CRITICAL ABORT]`.
6. Update tests — string-prefix assertions become field assertions.

The migration is mechanical and can land as a single PR. There is no
backwards-compat to preserve in the wire format because the field is
graph-internal — checkpoints written under the old format are
already invalidated by code changes.

## Consequences

- Routing becomes type-safe and exhaustively checkable.
- Abort metadata is queryable — the AgentOS UI can render
  "Aborted: news_evidence_missing" instead of just "Aborted".
- The `[CRITICAL ABORT]` literal can never collide with analyst
  content again.
- Per-reason metrics become trivial — group `abort_signal.reason`
  in the run-events log.
- `extract_abort_report` and `report_has_critical_abort` are
  deleted; calls to them won't compile until updated.

## Out of scope

- Resumability from a structured-abort checkpoint. The
  `recoverable` flag is metadata; building the resume tooling is a
  separate concern.
