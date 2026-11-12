# Interface Contracts (Member B)

Status: architecture draft (revised 2026-11-12 per review `docs/reviews/member-b-stage3-review-2026-11-12.md`). Typed shapes are **proposed design contracts** for C (test seams) and D (implementation); they are not implemented code. Unknown test IDs / implementation links remain **pending**. No compliance is claimed for anything not built or tested. Synthetic examples are **document examples**, not passing application tests.

This revision designs the required contracts rather than deferring them to D. External-owner items (final D1 approval, C's tests/rubric, E's enforcement, instructor layout) remain explicitly pending.

---

## 1. Module map and ownership (addresses B3-10)

Concrete planned paths so D does not invent architecture. Names are **proposed**; ownership is by team role.

| Planned path (new unless marked) | Responsibility | Owner (design / implement / test / enforce) |
|---|---|---|
| `tradingagents/runapi/__init__.py` | Package for the shared application boundary; **no `cli` import** | B / D / C / E |
| `tradingagents/runapi/context.py` | `RunContext`, `FrozenSnapshot`, canonicalization, deep immutability | B / D / C / E |
| `tradingagents/runapi/input_service.py` | `PortfolioInputService` (discover/precheck/freeze) — **noninteractive**, prompt-free | B / D / C / E |
| `tradingagents/runapi/checks.py` | `OutputChecker` (Q1–Q4, deterministic) | B / D / C / E |
| `tradingagents/runapi/result.py` | `RunResult`, `CheckResult`, findings, `InputError` schemas | B / D / C / E |
| `tradingagents/runapi/finalize.py` | `OutcomeFinalizer`, exception mapping | B / D / C / E |
| `tradingagents/runapi/persist.py` | Staging, commit, manifest, publication ordering | B / D / C / E |
| `tradingagents/runapi/events.py` | JSONL `EventSink` | B / D / C / E |
| `tradingagents/runapi/redact.py` | Central `Redactor` (sink boundary) | B / D / C / E |
| `tradingagents/runapi/execution.py` | **Shared application entry service** `run_analysis_api(...)` (see §5) | B / D / C / E |
| `cli/input_ui.py` | Interactive discovery/consent UI (prompts **only** here) | B / D / C / E |
| `cli/main.py`, `cli/run.py` (existing) | Thin adapters: call `execution.run_analysis_api` with confirmed input | adapted |
| `tradingagents/portfolio.py` (existing) | `PortfolioContext` model + `render`; upstream loader unchanged | preserved |
| `tradingagents/agents/context.py`, manager/trader prompts (existing) | Mode-aware wording; no-portfolio Hold meaning | adapted |
| `tradingagents/reporting.py`, `report_html.py` (existing) | Body rendering + final envelope header; projection-driven | adapted |

**Dependency rule:** `cli/*` → `tradingagents/runapi/*` → (engine, agents, portfolio, reporting). `tradingagents/runapi/*` must **not** import `cli`. This keeps the shared boundary usable without a terminal (B3-01, B3-10).

---

## 2. Design types and canonicalization (addresses B3-02, B3-03)

### 2.1 `InputMode`
```
InputMode = NO_PORTFOLIO | PORTFOLIO_PROVIDED
```
- `NO_PORTFOLIO`: holdings/cash unknown; nothing assumed.
- `PORTFOLIO_PROVIDED`: an explicitly selected, validated, frozen snapshot. An explicitly supplied empty `positions` list is a **flat** snapshot, not missing input.

### 2.2 Canonical fingerprint bytes (B3-03, F2)
The new provenance fingerprint is **SHA-256 (64 lowercase hex chars)** over a **canonical JSON byte string** of the normalized snapshot. Exact rules:

1. **Normalized object** contains exactly: `{"cash":…,"currency":…,"positions":[{"ticker":…,"quantity":…,"average_price":…}, …]}`. No other keys participate.
2. **Key order:** lexicographic ascending at every object level (`sort_keys=True`).
3. **Encoding:** UTF-8, **no BOM**, **no trailing newline**; bytes are `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")`.
4. **Separators:** `,` and `:` with **no whitespace** (`separators=(",", ":")`).
5. **String escaping:** JSON string escaping only (`ensure_ascii=False`, so non-ASCII tickers are emitted as UTF-8, not `\uXXXX`); no additional escaping. Tickers are trimmed and uppercased before serialization.
6. **Null/default handling:** an absent optional field and an explicit JSON `null` are the **same** and are serialized as the JSON token `null` (`average_price`, `cash`, `currency`).
7. **Number-token serialization (exact):** every numeric field is first converted by `to_canonical_number(x)`:
   - reject non-finite (`NaN`/`±Inf`) at validation (never reach canonicalization);
   - normalize `-0.0` to `0.0`;
   - if the value is integral and `|x| < 2**53`, emit the **integer token** (e.g., `10`, `1`, `0`), so `1` and `1.0` → token `1`;
   - otherwise emit Python `float.__repr__` (shortest round-trippable decimal, e.g., `150.5`, `0.1`).
   This defines the exact byte token; it is not "whatever JSON does".
8. **Positions sort — total order (no `None`/float comparison):** sort the canonical **row objects** by the composite key `(ticker_upper, to_canonical_number(quantity), price_key)` where `price_key = (0, 0.0)` when `average_price is None` and `(1, to_canonical_number(average_price))` otherwise (a tagged tuple: null sorts **before** any number; numeric compares numerically). Because `ticker_upper` is a string and is part of the key, **two different broker spellings that normalize to the same symbol but differ in spelling sort by their hashed spelling**, and a full-row tie is impossible unless all three hashed fields are equal (identical rows are interchangeable, so input order cannot change the digest). This is a **total order over every field that participates in the digest**, so reordering input never changes the digest and no valid portfolio is rejected by sorting.
9. **Symbol spelling:** `ticker` is hashed using the **original spelling** as supplied (trimmed, uppercased). Holdings keep their spelling (`portfolio.py:40-68`); alias matching is a runtime concern, not identity. Two files differing only by broker alias spelling are **different** provenance and therefore **different** digests (both are accepted; ordering above remains total).
10. **Excluded fields:** `basename`, filesystem path, mtime, `portfolio_as_of`, `as_of_basis`, `mode` are recorded separately in metadata, **not** in the content digest.

> Invariant: INV-05. Upstream truncated 12-char checkpoint fingerprint (`portfolio.py:70-72`, `trading_graph.py:158`) is **preserved unchanged** and unrelated to this digest.

#### 2.2.1 Exact canonical-byte examples (verified against the rules above)
Row order after sorting is shown; bytes are exactly the string inside quotes.

- **Reason A — null vs numeric price (reversed input):**
  - Input `[("AAPL",10,None),("AAPL",10,2.0)]` and reversed `[("AAPL",10,2.0),("AAPL",10,None)]` both serialize to
    `{"cash":null,"currency":null,"positions":[{"average_price":null,"quantity":10,"ticker":"AAPL"},{"average_price":2,"quantity":10,"ticker":"AAPL"}]}` → **equal digest** (null sorts before numeric; `10`/`2` are integer tokens).
- **Reason B — broker-alias tie (reversed input):**
  - Input `[("BRK.B",5,100.0),("BRK-B",5,100.0)]` and reversed both serialize to
    `{"cash":null,"currency":null,"positions":[{"average_price":100,"quantity":5,"ticker":"BRK-B"},{"average_price":100,"quantity":5,"ticker":"BRK.B"}]}` → **equal digest** (`"BRK-B"` < `"BRK.B"`; spelling is part of the sort key). Reindexing the **spelling** (e.g., `BRK.B`→`BRK-B` on the other row) is a **different** portfolio by rule 9 and yields a different digest.
- **Reason C — numeric `1` vs `1.0`:**
  - `[("MSFT",1,50)]` cash `1` and `[("MSFT",1.0,50.0)]` cash `1.0` both serialize to
    `{"cash":1,"currency":null,"positions":[{"average_price":50,"quantity":1,"ticker":"MSFT"}]}` → **equal digest**.
- **Reason D — missing vs explicit null:** a position with absent `average_price` and one with explicit `null` serialize identically (`"average_price":null`) → **equal digest**.
- **Reason E — full example with cash:** `[("AAPL",10,150.5),("MSFT",5,None)]`, cash `2500.0`, currency `"USD"` →
  `{"cash":2500,"currency":"USD","positions":[{"average_price":150.5,"quantity":10,"ticker":"AAPL"},{"average_price":null,"quantity":5,"ticker":"MSFT"}]}`
  → SHA-256 `45f07d9eb3359b059525da0cee26f8a9810269dad11ffb4c42e1dcc7072cef72`.
- **Expected difference:** changing `quantity` from `10` to `10.5`, adding a position, or altering cash/currency changes the digest.

These are **document examples** checked against the written rules, not passing application tests.

### 2.3 Deep immutability (B3-03)
Upstream `PortfolioContext` holds a mutable `list[Position]` of mutable model instances. `RunContext` immutability alone is insufficient. Design:

- The frozen snapshot is stored as **immutable value tuples**:
  ```
  FrozenPositions = tuple[tuple[str, float, float | None], ...]   # (ticker, quantity, average_price)
  FrozenSnapshot = (basename, cash: float|None, currency: str|None,
                    positions: FrozenPositions, fingerprint_sha256, portfolio_as_of)
  ```
- `RunContext` is a frozen dataclass holding these tuples; it exposes **no mutable accessor**.
- When agents need a `PortfolioContext`, the boundary **constructs a fresh `PortfolioContext`** from the frozen tuples (defensive copy) on each use; it never hands out a shared mutable object. Mutation of that constructed object cannot affect the stored identity.
- The canonical bytes are computed from the frozen tuples, so they are stable regardless of later copies.

### 2.4 `RunContext`
```
RunContext (frozen dataclass) {
  run_id: str
  ticker: str
  analysis_date: str
  mode: InputMode
  snapshot: FrozenSnapshot | None      # None ⇔ NO_PORTFOLIO
  unverified_holdings: bool
  provider_transmission_disclosed: bool
  consent_state: FROZEN | CONFIRMED    # see §4
}
```
`snapshot is None` **iff** `mode == NO_PORTFOLIO`. `consent_state=FROZEN` ⇒ run not authorized; a snapshot existing does **not** authorize (B3-01, §4).

---

## 3. Complete schemas and conditional fields (addresses B3-02)

All projections below are **separately defined** and **never** serialize the portfolio payload or full `RunContext`. Field names use the selected spelling.

### 3.1 `InputError`
```
InputError {
  kind: "MALFORMED_JSON" | "MISSING_POSITIONS" | "MISSING_QUANTITY" | "NONFINITE_NUMBER"
        | "WRONG_SCALAR_TYPE" | "UNREADABLE_PATH" | "AS_OF_MISMATCH" | "FLAG_CONFLICT"
  basename: str | null          # null when path unreadable before basename known
  field: str | null             # e.g. "positions[2].quantity"
  detail: str                   # redacted, no file contents/credentials
}
```

### 3.2 `Finding`
```
Finding {
  rule: "Q1" | "Q2" | "Q3" | "Q4" | "CHECK_ERROR"
  status: "BLOCKING"
  detail: str                   # redacted
}
```

### 3.3 `CheckResult` (F3 — case table)
```
CheckResult {
  output_check: "PASSED" | "NEEDS_REVIEW" | "NOT_RUN"
  findings: Finding[]
}
```
Authoritative case table (**checker is invoked only on the completed path**, §6):

| Case | `output_check` | `findings` | When |
|---|---|---|---|
| All rules hold | `PASSED` | `[]` (exactly empty) | Completed run; Q1–Q4 all hold |
| Any rule broken OR checker exception | `NEEDS_REVIEW` | **≥ 1** blocking finding (Q1/Q2/Q3/Q4, or a single `CHECK_ERROR` on exception) | Completed run |
| Run incomplete | `NOT_RUN` | `[]` (exactly empty) | Checker **not invoked**; assigned by finalizer branch (§6) |

Invariants (H2 — empty-findings equivalence qualified to **completed** runs): **Completed** ⇒ `PASSED ⇔ findings==[]` and `NEEDS_REVIEW ⇒ findings≠[]`; **Incomplete** ⇒ `NOT_RUN` with `findings==[]` (checker not invoked). There is no global `PASSED ⇔ findings==[]` — `NOT_RUN` also has empty findings.

### 3.4 `RunResult` (returned to caller)
```
RunResult {
  run_id: str
  ticker: str
  analysis_date: str
  input_mode: InputMode
  run_outcome: "COMPLETED" | "INCOMPLETE"
  stop_reason: null | "MODEL_FAILURE" | "DATA_FAILURE" | "INTERNAL_ERROR"
               | "PERSISTENCE_ERROR" | "INTERRUPTED"
  final_rating: null | "Buy" | "Overweight" | "Hold" | "Underweight" | "Sell" | "REVIEW"
  output_check: "PASSED" | "NEEDS_REVIEW" | "NOT_RUN"
  findings: Finding[]
  manifest_path: str | null     # non-null iff the run directory was published (§7)
  report_path: str | null       # non-null iff the report was published (§7)
}
```
**Conditional fields (enforced by finalizer):**
- `COMPLETED` ⇒ `final_rating != null` and `stop_reason == null`.
- `INCOMPLETE` ⇒ `final_rating == null`, `output_check == "NOT_RUN"`, `findings == []`, `stop_reason != null`.

### 3.5 Safe input metadata projection (for sinks; never the payload)
```
SafeInputMetadata {
  run_id, ticker, analysis_date,
  input_mode: InputMode,
  basename: str | null,                 # null iff NO_PORTFOLIO
  fingerprint_sha256: str | null,       # null iff NO_PORTFOLIO (64 hex)
  portfolio_as_of: str | null,          # null iff NO_PORTFOLIO
  as_of_basis: "USER_CONFIRMED" | null  # null iff NO_PORTFOLIO
}
```
The `null` conditions are **portfolio-only** (mode-dependent); distinct from **outcome-conditional** `RunResult` fields.

### 3.6 `SafeRunMetadata` (durable run record; never the payload) — F3
```
SafeRunMetadata {
  schema_version: "1",
  run_id, ticker, analysis_date, input_mode,
  basename: str|null, fingerprint_sha256: str|null, portfolio_as_of: str|null, as_of_basis: "USER_CONFIRMED"|null,
  run_outcome: "COMPLETED" | "INCOMPLETE",
  stop_reason: ... | null,               # §3.4 conditional
  final_rating: ... | null,              # §3.4 conditional — NOW CARRIED IN THE DURABLE RECORD
  output_check: "PASSED" | "NEEDS_REVIEW" | "NOT_RUN",
  findings: Finding[],
  code_version: str,                     # tradingagents.__version__
  source_revision: str | null,           # separate source identifier, e.g. git describe or "unknown" (§3.7)
  prompt_hash: str,                      # §3.8
  effective_config: EffectiveConfig,     # §3.7
  start_ts_utc: str, end_ts_utc: str     # ISO-8601 UTC; set once at finalize
}
```
The **same** `final_rating` spelling/conditional rules as `RunResult` apply. Timestamps are captured once at finalize and are never mutated later.

### 3.7 `EffectiveConfig` (safe, behaviour-relevant; secrets/endpoints omitted) — F3
```
EffectiveConfig {
  llm_provider, deep_think_provider, deep_think_llm, quick_think_provider, quick_think_llm,
  analysts: str[], max_debate_rounds: int, max_risk_discuss_rounds: int,
  output_language: str,
  temperature: float | null, max_tokens: int | null,          # behaviour-affecting (baseline keys if set)
  context_cap_tokens: int, compaction_threshold_tokens: int,  # the designed context budget (ADR §Context)
  data_vendors: map, tool_vendors: map
}
```
Derived from `run_settings()` (`trading_graph.py:255-275`) **plus** the behaviour-affecting keys this design introduces (`temperature`, `max_tokens`, context cap/threshold). `backend_url`, keys, OAuth tokens, local paths are **never** included. `source_revision` is recorded **separately** from `code_version` (upstream `version` stays `0.7.1`; the revision id identifies the actual source state and is `"unknown"` when unavailable).

### 3.8 `prompt_hash` (deterministic input spec) — F3
- Inventory: the **template set** actually used = (a) identity/context instruction templates, (b) selected analyst templates, (c) trader + research/portfolio-manager templates, (d) frozen notice/disclaimer strings, (e) the mode-aware legend variants selected for this run.
- Serialization: an ordered list `[(template_id, template_text), …]` sorted by `template_id`; each entry serialized as `template_id + "\n" + template_text`; entries joined by `"\n\n"`; UTF-8, no BOM, no trailing newline; `prompt_hash = SHA-256(bytes)` (64 hex).
- **Dynamic holdings/evidence are excluded** (they vary per run and are captured by the fingerprint/state, not the prompt template). Editing any template or frozen string changes `prompt_hash`. `template_id` values are stable identifiers (e.g., `analyst.market`, `trader`, `manager.portfolio`, `frozen.disclaimer`, `legend.no_portfolio`).

### 3.9 `Event` (JSONL)
```
Event {
  run_id, ticker,
  node: "input" | "engine" | "output",
  ts: str (UTC ISO-8601),
  elapsed_ms: int (>=0, monotonic),
  event: str,                 # e.g. input.selection, input.consent, run.terminal, output.check, output.persist
  event_outcome: str          # progress vocabulary, separate from run_outcome
}
```
Exactly one `event=run.terminal` logical decision per run (§7.5).

### 3.10 Final manifest (`manifest.json`) — F1/F3
```
Manifest = SafeRunMetadata + {
  report_paths: { markdown: str|null, html: str|null },
  terminal_event: { logical: "run.terminal", durable: bool }   # durable = JSONL terminal write succeeded before publication
}
```
The manifest is written **once**, atomically, **as part of the single publication commit** (§7), and contains **no** positions/cash/other-position list and no secrets. `terminal_event.durable` is known **before** publication because the terminal event is written **before** the commit (or its outcome is decided then) — a later append never changes the immutable manifest.

#### 3.10.1 Manifest examples (document examples; values illustrative)
Completed, portfolio-provided (fingerprint from §2.2.1 Reason E):
```
{"schema_version":"1","run_id":"20261112T101500Z-ab12cd","ticker":"AAPL","analysis_date":"2026-11-12",
 "input_mode":"PORTFOLIO_PROVIDED","basename":"b.json",
 "fingerprint_sha256":"45f07d9eb3359b059525da0cee26f8a9810269dad11ffb4c42e1dcc7072cef72",
 "portfolio_as_of":"2026-11-12","as_of_basis":"USER_CONFIRMED",
 "run_outcome":"COMPLETED","stop_reason":null,"final_rating":"Overweight","output_check":"PASSED","findings":[],
 "code_version":"0.7.1","source_revision":"git:abc1234","prompt_hash":"<64hex>",
 "effective_config":{"llm_provider":"openai","deep_think_llm":"gpt-x","quick_think_llm":"gpt-y","analysts":["market","news"],"max_debate_rounds":2,"max_risk_discuss_rounds":2,"output_language":"English","temperature":0.2,"max_tokens":4096,"context_cap_tokens":24000,"compaction_threshold_tokens":19200,"data_vendors":{},"tool_vendors":{}},
 "start_ts_utc":"2026-11-12T10:15:00Z","end_ts_utc":"2026-11-12T10:18:22Z",
 "report_paths":{"markdown":"reports/complete_report.md","html":"reports/complete_report.html"},
 "terminal_event":{"logical":"run.terminal","durable":true}}
```
Incomplete, no-portfolio (persistence failure example):
```
{"schema_version":"1","run_id":"20261112T090000Z-ef34gh","ticker":"NVDA","analysis_date":"2026-11-12",
 "input_mode":"NO_PORTFOLIO","basename":null,"fingerprint_sha256":null,"portfolio_as_of":null,"as_of_basis":null,
 "run_outcome":"INCOMPLETE","stop_reason":"PERSISTENCE_ERROR","final_rating":null,"output_check":"NOT_RUN","findings":[],
 "code_version":"0.7.1","source_revision":"git:abc1234","prompt_hash":"<64hex>",
 "effective_config":{...},"start_ts_utc":"2026-11-12T09:00:00Z","end_ts_utc":"2026-11-12T09:03:10Z",
 "report_paths":{"markdown":null,"html":null},"terminal_event":{"logical":"run.terminal","durable":true}}
```
(Conditional rules hold: COMPLETED has a rating and `stop_reason=null`; INCOMPLETE has `final_rating=null`, `output_check=NOT_RUN`, `findings=[]`, a `stop_reason`, and null report paths.)

---

## 4. Input-mode state machine (addresses B3-08; both modes complete)

Interactive discovery/consent lives only in `cli/input_ui.py`. The **noninteractive service** (`input_service.py`) accepts explicit inputs/paths.

```
START
 ├─ explicit --portfolio PATH ─────────────► VALIDATING_EXPLICIT
 ├─ explicit --without-portfolio ──────────► NO_PORTFOLIO_FREEZE
 └─ interactive, no explicit flags ────────► DISCOVERING
DISCOVERING
 ├─ eligible files present ──► SELECTING ──cancel──► CANCELLED
 ├─ missing or empty dir ────► NO_PORTFOLIO_CONFIRM   (never described as "empty" if errored)
 └─ directory read error ────► DIR_ERROR ──retry──► DISCOVERING
                              └──choose no-portfolio──► NO_PORTFOLIO_CONFIRM
                              └──cancel──► CANCELLED
SELECTING ──file chosen──► VALIDATING
VALIDATING ──invalid──► INVALID ──reselect──► SELECTING / ──cancel──► CANCELLED
VALIDATING_EXPLICIT ──(noninteractive: --portfolio-as-of D required, D == analysis date)──►
   ──valid──► PORTFOLIO_FREEZE   ──invalid/as-of-mismatch/flags-conflict──► INPUT_ERROR (zero run)
VALIDATING ──valid──► PORTFOLIO_FREEZE
PORTFOLIO_FREEZE  (freeze bytes → FrozenSnapshot; consent_state=FROZEN)
   ──interactive: show notice (basename, D, unverified/as-of, provider-transmission)──► AWAITING_CONSENT
   ──noninteractive: explicit --portfolio already expresses consent──► CONFIRMED
AWAITING_CONSENT ──yes──► CONFIRMED ; ──no/EOF──► CANCELLED
NO_PORTFOLIO_FREEZE
   ──interactive: show frozen no-portfolio notice──► NO_PORTFOLIO_CONFIRM
   ──noninteractive: --without-portfolio expresses consent──► CONFIRMED
NO_PORTFOLIO_CONFIRM ──yes──► CONFIRMED ; ──no/EOF──► CANCELLED
CONFIRMED ──► RUNNING
CANCELLED / INPUT_ERROR → zero graph, zero LLM, no completed run
```

- **Both modes** reach a frozen candidate and explicit confirmation (interactive) or explicit flag consent (noninteractive).
- **Noninteractive flag rules:** neither `--portfolio` nor `--without-portfolio` ⇒ `INPUT_ERROR` (zero calls); **both** ⇒ `INPUT_ERROR`; `--portfolio` without `--portfolio-as-of` ⇒ `INPUT_ERROR`; `--portfolio-as-of` with `--without-portfolio` ⇒ `INPUT_ERROR`; `--portfolio-as-of D` ≠ analysis date ⇒ `AS_OF_MISMATCH`.

### 4.1 Consent as explicit transitions (B3-01; immutability ≠ bypass prevention)
| From | Trigger | To | Guard |
|---|---|---|---|
| `FROZEN` (PORTFOLIO_FREEZE/NO_PORTFOLIO_FREEZE) | interactive Yes, or valid explicit flag | `CONFIRMED` | notice for portfolio shown first (interactive) |
| `FROZEN` | interactive No/EOF/cancel | `CANCELLED` | zero run |
| `CONFIRMED` | (any) | `RUNNING` | **only** path to `execution.run` |

`execution.run_analysis_api` **rejects** a `RunContext` whose `consent_state != CONFIRMED`. A frozen snapshot existing does **not** authorize execution; the transition does.

- **No silent reread:** after freeze the file is never reopened; frozen bytes are the sole input.
- **Disclosure sequencing:** only the **notice** precedes consent; holdings are transmitted to the provider **only after** `CONFIRMED` (during `RUNNING`). No provider transmission before consent.

---

## 5. Shared CLI/API execution boundary (addresses B3-01, B3-10)

The **common application entry service** routes **every supported entry point** through the mandatory checks/finalization/persistence:

```
# tradingagents/runapi/execution.py  (prompt-free; no cli import)
run_analysis_api(
    run_context: RunContext,          # consent_state must be CONFIRMED
    graph_factory: Callable[..., Engine],  # injectable for tests; default TradingAgentsGraph
    event_sink: EventSink,
    redactor: Redactor,
) -> RunResult
sequence: validate_consent → engine.stream_run(portfolio or None)
          → render_body → check → finalize → stage → publish → terminal event
```

### 5.1 Entry points and which boundary they traverse
| Entry point | Interaction | Boundary traversal | Requirement coverage |
|---|---|---|---|
| CLI interactive (`cli/main.py`) | prompts in `cli/input_ui.py` | freezes+confirm → `run_analysis_api` | Full (FR/NFR) |
| CLI noninteractive (flags) | none | flags → freeze → `run_analysis_api` | Full |
| **Supported project API** (`tradingagents.runapi.execution.run_analysis_api`) | none | supplies a `RunContext` (built via input service or explicit `portfolio`/`None`) → `run_analysis_api` | Full |
| Low-level engine primitive (`TradingAgentsGraph.propagate/stream_run`) | none | **raw**; **does not** traverse the boundary | **Reduced** — see §5.3 |

### 5.2 Supported project API signature
The upstream engine signature is **preserved** (`trading_graph.py:167,293`: `portfolio=None|PortfolioContext`). A programmatic caller wanting the full contract uses:
```
from tradingagents.runapi.execution import run_analysis_api
from tradingagents.runapi.input_service import freeze_explicit  # builds a FROZEN RunContext
ctx_frozen = freeze_explicit(ticker, analysis_date, portfolio=PortfolioContext(...) | None)  # no prompt; consent_state=FROZEN
ctx_confirmed = ctx_frozen.confirm()                      # explicit programmatic consent transition
result: RunResult = run_analysis_api(ctx_confirmed, event_sink=..., redactor=...)
```
- **Consent is consistent across all entry points:** `freeze_explicit` **always** returns `consent_state=FROZEN`; a programmatic caller must perform an explicit `confirm()` transition (the programmatic expression of consent; no prompt, no provider transmission before `run_analysis_api`). This matches the CLI/interactive rule that a frozen context is not executable.
- `freeze_explicit(..., portfolio=None)` ⇒ `NO_PORTFOLIO` RunContext with `basename/fingerprint/as_of=null`. `portfolio=PortfolioContext(...)` (in-memory) ⇒ frozen snapshot with **synthetic provenance**: `basename="<in-memory>"`, `fingerprint_sha256=<64-hex over §2.2 canonical bytes>`, `portfolio_as_of=<analysis_date>`, `as_of_basis="USER_CONFIRMED"` (the caller asserts the in-memory book is intended for that date).
- This path runs checks/finalization/redaction/single-commit publication — no compliance gap (B3-01 resolved at design level).

### 5.3 Low-level primitive (precise scope; A approval required for reduced coverage)
`TradingAgentsGraph.propagate/stream_run/create_run_state` remain available unchanged for baseline compatibility and upstream tests. They **do not** provide the output checker, outcome finalizer, redaction, manifest or events. Scope and honesty:
- Use is legitimate for baseline/existing upstream behaviour and for engine-level tests only.
- A caller using **only** the raw primitive **does not** satisfy FR-006/FR-007/NFR-002/003/004. This is a **declared, scoped low-level compatibility path**; **A must approve** any excluded requirement coverage if a product-facing path relies on it (R-API, pending A). It is not a D design task; only A's acceptance of reduced coverage is pending.
- **Mandatory CLI traversal:** the CLI (`cli/main.py`, `cli/run.py`) **must** call `run_analysis_api` for all product runs; it may not call the raw primitive directly. The raw primitive is not a product entry point.

---

## 6. Render / check / final envelope ordering (addresses B3-04)

**Problem fixed:** the check must run on content that does *not* yet contain its own result, yet the delivered header must display the check result. Resolution: separate the **immutable checked body** from the **trusted final envelope**.

### 6.1 Two-part document
- **Body** (model-generated sections + trusted frozen notice/disclaimer): rendered once from `final_state` + `RunContext`, **redacted before check**.
- **Pre-check provenance fragment** (trusted, deterministic): the exact header lines Q2 will inspect — analysis date, input mode, basename, full-64 fingerprint, as-of/basis — rendered from `SafeInputMetadata` **before** the check. This is the object Q2 compares; it is not the checker comparing metadata to itself, because it is an independently produced text fragment.
- **Envelope** (trusted): the final delivered header, built **after** the check from `SafeRunMetadata` (which now includes outcome/check). It must byte-match the pre-check provenance fragment for its Q2 fields (verified again before publication, §6.4).

### 6.2 Single authoritative check — completed path only (F4)
```
1. final_state  (or an exception → go to 6.3 INCOMPLETE branch; checker NOT called)
2. body = render_body(final_state, RunContext)                 # trusted strings inserted
3. body = redactor.scrub(body)                                 # redaction BEFORE check
4. provenance_fragment = render_provenance(SafeInputMetadata)  # trusted header text Q2 inspects
5. final_rating = run_rating(final_state)  |  REVIEW           # deterministic
6. CheckResult = OutputChecker.evaluate(                        # ONE authoritative call
        trusted: SafeInputMetadata,     # Q2 authoritative expected values (explicit argument)
        provenance_fragment: str,       # Q2 subject (independently rendered trusted text, compared to `trusted`)
        final_rating: str,              # Q1 subject
        rendered_body: str)             # Q3/Q4 subject (disclaimer excluded from Q4)
   # if the checker raises → CheckResult{NEEDS_REVIEW,[CHECK_ERROR]} (fail closed, single decision)
7. result = OutcomeFinalizer.finalize(graph_returned=True, final_rating, exc=None)  # COMPLETED
8. envelope = build_envelope(SafeRunMetadata(result, CheckResult))   # uses the FROZEN CheckResult; no second verdict
9. verify_envelope_header_matches(envelope, trusted)     # publication-time guard vs AUTHORITATIVE metadata (§6.4)
10. final_doc_md = envelope + body ; final_doc_html = render_html(envelope, body)
11. stage → single publication commit (§7)
```
- The checker is invoked **exactly once** on the completed path; the envelope consumes the **frozen** `CheckResult`.
- **Q2 has a real subject and explicit trusted values:** Q2 compares `provenance_fragment` (independently rendered pre-check text) against the **explicitly supplied trusted `SafeInputMetadata`** argument. A fragment whose basename/fingerprint/as-of differs from trusted metadata produces a **Q2** finding, not a guaranteed pass. The trusted metadata is a call argument, not ambient state.

### 6.3 Incomplete branch — checker bypassed (F4)
```
1. engine raised OR graph did not return a usable final_state
2. result = OutcomeFinalizer.finalize(graph_returned=False, final_rating=None, exc=exc)
3. CheckResult = CheckResult{output_check:"NOT_RUN", findings:[]}   # assigned directly; checker NOT invoked
4. envelope = build_envelope(SafeRunMetadata(result, CheckResult))   # INCOMPLETE, NOT_RUN, no rating
5. no successful report body is published as PASSED; partial artifacts labelled INCOMPLETE (§7)
```
The checker signature never receives graph-returned data on this path, so there is no contradictory double verdict.

### 6.4 Envelope verification and source-of-truth (F4, H3)
- `OutputChecker.evaluate(trusted, provenance_fragment, final_rating, rendered_body)` calls no provider. Q1 = rating readable; **Q2 = every Q2 field in `provenance_fragment` equals the explicit trusted `SafeInputMetadata`** argument; Q3 = disclaimer present in body; Q4 = prohibited phrases absent in body (disclaimer excluded).
- **Publication-time guard — against authoritative metadata:** before the commit, the build verifies that the envelope's Q2 fields equal the **trusted `SafeInputMetadata`** (the same authoritative expected values). The guard does **not** compare the envelope to the possibly-defective `provenance_fragment`; it validates both the fragment's finding (already recorded by the checker) and the delivered envelope against the authoritative values.
- **Q2-defect path (consistent):** if the fragment disagrees with trusted metadata, the checker records a `Q2` finding (`NEEDS_REVIEW`) and that finding is **retained**; the envelope is built from trusted metadata (a **corrected** header) and passes the guard because it matches authoritative values. The run delivers the corrected header labelled `NEEDS_REVIEW` with the original Q2 finding — it is neither silently marked clean nor claimed to have equal-but-unequal values.
- **Single source for the disclaimer:** the disclaimer is rendered **once** into the body from the frozen string; the envelope references its presence (Q3) rather than re-emitting a second copy, avoiding body/envelope duplication mismatch.
- **Redaction precedes checks**, so a checked artifact cannot later be invalidated by redaction.

### 6.5 Walkthroughs (synthetic; document examples; verified against §6.2–§6.4)
- **Completed-PASS (no-portfolio):** `final_rating="Hold"`; `provenance_fragment` renders `input_mode=NO_PORTFOLIO`, basename/fingerprint/as-of `null`; body has disclaimer, no prohibited phrase → `CheckResult{PASSED,[]}`; `RunResult{COMPLETED, stop_reason=null, final_rating="Hold", output_check=PASSED}`; envelope shows PASSED; guard passes (envelope matches trusted metadata).
- **Completed-REVIEW (Q2 defect):** renderer bug renders `basename="c.json"` in the `provenance_fragment` while trusted `SafeInputMetadata.basename="b.json"` → Q2 fails on the single checker call → `CheckResult{NEEDS_REVIEW,[Q2]}` (finding retained); `RunResult{COMPLETED, output_check=NEEDS_REVIEW}`; the envelope is built from trusted metadata (`b.json`, corrected) and the guard passes because it matches the **authoritative** metadata; the delivered header shows `b.json` and the retained Q2 finding, outcome not silently clean.
- **Completed-REVIEW (Q4):** body contains `guaranteed profit` outside disclaimer → `Finding{Q4}`; `NEEDS_REVIEW`.
- **Checker-error:** checker raises on the single call → `CheckResult{NEEDS_REVIEW,[CHECK_ERROR]}`; graph returned so `COMPLETED`; `output_check=NEEDS_REVIEW`; no second call to disagree.
- **Graph-failure (INCOMPLETE):** exception → INCOMPLETE branch; **checker not invoked**; `output_check=NOT_RUN`, `final_rating=null`, `stop_reason` set; nothing published as PASSED.

### 6.6 Rendering order for agents (identity vs display)
Canonicalization sorts positions for hashing; `PortfolioContext.render()` keeps upstream ordering for the prompt. Identity and display are intentionally separate; neither mutates the frozen tuple.

---

## 7. Staging, single publication commit, and terminal-event ordering (addresses F1)

### 7.1 Single publication commit point
The run directory is the unit of atomic publication on the same filesystem:
```
STAGING dir: <results>/_staging/<run_id>/         # not visible as a successful run
  reports/complete_report.md  (and .html if enabled)   # final envelope + checked body
  manifest.json                                        # fully populated incl. terminal_event.durable
COMMIT:  os.replace/rename  <results>/_staging/<run_id>  ->  <results>/<ticker>/<run_id>/
```
- **One commit point.** Everything the manifest describes (report MD/HTML, manifest itself) is written into the **staging** directory **first**; the **only** publication action is a single atomic directory rename. Before the rename, nothing exists at the published path; after it, a complete, self-consistent run directory exists.
- **No success is visible before the commit.** There is no earlier `rename` of the report into the published location; the "report staged but unpublished" state is real because the report lives only under `_staging`.
- **Terminal event ordering (truthful durability):** the **logical** terminal decision is computed before commit. The **JSONL terminal event is appended to the staging `events.jsonl` before the commit**, so its success/failure is **known before** the manifest is finalized. `terminal_event.durable = (jsonl terminal append succeeded)`. A later event append is **not** part of the immutable manifest's claim; best-effort events written after commit are separate and cannot change `manifest.json`.
- **Reader behaviour:** a run directory is a valid published run iff it exists at `<results>/<ticker>/<run_id>/` (the rename completed). `_staging/**` is never treated as a published run. Readers may ignore `_staging`.

### 7.2 Sink criticality
| Sink | Criticality | Rule (with single-commit) |
|---|---|---|
| Report MD (and HTML if enabled) | **Critical** | Written to staging; part of the commit unit |
| Manifest | **Critical** | Written to staging with final `terminal_event.durable`; part of the commit unit |
| JSONL terminal event | **Best-effort (not critical)** | Appended to staging **before** commit; its outcome sets `terminal_event.durable` but **does not** block publication and does **not** change the logical outcome |
| Other JSONL progress events | Best-effort | May be appended pre- or post-commit; failure ⇒ redacted note; never changes the immutable manifest |
| State JSON / message log | Best-effort | Written to staging or post-commit; failure ⇒ redacted note; does not flip a completed decision |

### 7.3 Failure mapping (one per path)
- **Critical staging write fails** (report or manifest) **before commit:** no rename performed; nothing appears at the published path; result `INCOMPLETE`, `stop_reason=PERSISTENCE_ERROR`, `final_rating=null`, `output_check=NOT_RUN`, `findings=[]`, `report_path=null`, `manifest_path=null`. Staging dir is cleaned or left under `_staging` (not published).
- **Commit rename fails:** same as above — nothing published; typed `PERSISTENCE_ERROR`.
- **Best-effort sink fails (progress event / state log / message log):** the commit still proceeds; outcome is unchanged (`COMPLETED`/…); a redacted note is recorded; `terminal_event.durable` reflects the **terminal** append only.
- **Terminal-event append to staging fails (best-effort):** the **logical outcome is preserved** (`COMPLETED` if the graph returned); `terminal_event.durable=false` is recorded in the staging manifest **before** commit; the run directory is still published (report+manifest valid). This is **not** a critical failure and does **not** return `PERSISTENCE_ERROR`.
- **Logical outcome revision:** `OutcomeFinalizer` produces the logical outcome; only a **critical report/manifest staging-or-commit** failure (before any publication) revises the returned result to `INCOMPLETE/PERSISTENCE_ERROR`. Since nothing is published before commit, no published PASSED/COMPLETED can contradict the returned result.
- **Full-disk/power-loss durability:** out of scope; `PERSISTENCE_ERROR` is the cooperative contract.

### 7.4 Reconciliation with earlier finalization
`OutcomeFinalizer` sends the logical outcome and `terminal_event.durable` into the staging manifest **before** commit. If critical persistence fails, the **returned** result is revised to `INCOMPLETE/PERSISTENCE_ERROR` (satisfying INV-08); nothing was published, so there is no stale success artifact.

### 7.5 Chronological failure walkthroughs (document examples; states verified against §7.1–§7.4)
Legend: `VISIBLE` = present at published path; `STAGED` = under `_staging` only.

- **(a) Report staging write fails:** after staging the manifest is attempted? **No** — report write fails first → abort; no manifest, no commit. `STAGED`: partial report maybe; `VISIBLE`: nothing; returned `INCOMPLETE/PERSISTENCE_ERROR`, rating null, NOT_RUN, `report_path=null`, `manifest_path=null`.
- **(b) Manifest staging write fails:** report written to staging; manifest write fails → abort before commit; `STAGED`: report; `VISIBLE`: nothing; returned `INCOMPLETE/PERSISTENCE_ERROR`; no paths. No published COMPLETED exists.
- **(c) Final publication (rename) fails:** staging complete (report+manifest+terminal event); rename fails → `STAGED`: full run; `VISIBLE`: nothing; returned `INCOMPLETE/PERSISTENCE_ERROR`; no paths. Reader sees no published run.
- **(d) Best-effort JSONL progress write fails (after terminal already staged):** commit proceeds; `VISIBLE`: full run with `manifest.terminal_event.durable=true` (terminal append succeeded); returned `COMPLETED/…`; a redacted note about the dropped progress event. Immutable manifest unchanged by the dropped progress event.
- **(e) Terminal-event append to staging fails (best-effort):** `terminal_event.durable=false` recorded in the staging manifest **before** commit; commit still publishes the run directory (report+manifest valid); returned outcome is the **logical outcome** (COMPLETED if graph returned) — **not** PERSISTENCE_ERROR; a redacted note. The manifest truthfully states the terminal event is **not durable**; no later append alters it.

No walkthrough publishes a report that contradicts the returned terminal result.

---

## 8. CLI / API contract changes (intentional)
- Added: `--without-portfolio`; `--portfolio-as-of D`. Preserved: `--portfolio PATH` (may be outside `PORTFOLIO_DIR`; parent not scanned).
- Prompts suppressed under explicit flags; conflicts ⇒ `InputError` (no default). Intentional CLI changes (FR-002) recorded in ADR; not accidental compatibility failures.

## 9. Escaping and provenance values
- HTML escapes all model/file/provenance values (`report_html.py:10,226,255`); envelope values escaped too. Header uses `SafeInputMetadata`, never the payload.

## 10. Evaluation population interface (addresses B3-11)

NFR-006 requires completion accounting over **started fresh runs**, with pre-run cancellations counted separately and **zero-completed ⇒ insufficient evidence**. Defined interface (owner component: evaluation data model, proposed `tradingagents/runapi/result.py` `RunRecord`; aggregation is a reporting concern for C/D):

```
RunRecord (one per attempt; persisted only in evaluation datasets, NOT in the run manifest)
  attempt_id: str
  category: "STARTED" | "PRE_RUN_REJECTED" | "PRE_RUN_CANCELLED"
  run_outcome: "COMPLETED" | "INCOMPLETE" | null   # null for pre-run categories
  output_check: "PASSED" | "NEEDS_REVIEW" | "NOT_RUN" | null
  stop_reason: ... | null
  controlled_change: {factor: str, value: str} | null   # for before/after experiments
```
Aggregation (design):
- `completion_fraction = count(category=STARTED and run_outcome=COMPLETED) / count(category=STARTED)` (pre-run categories excluded from the denominator but reported separately).
- Report `completed_count`, `needs_review_count`, `incomplete_reason_counts`, `pre_run_rejected`, `pre_run_cancelled`.
- `completed_count == 0` ⇒ **insufficient evidence** (never a passing quality result).
- A pre-run attempt records **no** `run_outcome`, creates **no** completed artifact, and is never counted as a started run.
- Controlled before/after experiments carry `controlled_change` and are labelled as changed-factor comparisons; repeated fixed-condition benchmarks require matching controls. Exact scoring/threshold is C/A's (pending).

## 11. Pending (external owners)
Final D1/schema (A); C's test IDs, rubric/threshold, and independent evidence; E enforcement; instructor layout. A must approve any reliance on the reduced-coverage low-level primitive (§5.3).
