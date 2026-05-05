# Detailed Run I/O Report - MSFT 2026-04-29

Report date: 2026-05-01  
Repository: `tradingagents-flint-shadow`  
Run analyzed: MSFT shadow run, trade date `2026-04-29`, selected analyst `news`  
Primary evidence:

- State log: `output/logs/MSFT/TradingAgentsStrategy_logs/full_states_log_2026-04-29.json`
- Raw tool provenance: `output/provenance/MSFT/2026-04-29/raw_tool_outputs.jsonl`
- Raw tool manifest: `output/provenance/MSFT/2026-04-29/raw_tool_outputs_manifest.json`

This report uses the C4 pipeline view from `docs/flint/TRADINGAGENTS_C4_PIPELINE.md` and expands it into every material input/output observed in one completed run. It also applies the current upgraded rigor layer: raw source objects, required source citations, pre-synthesis scope audit, six-factor scorecard, and quality failure on citation or ticker/entity defects.

## Executive Summary

The MSFT run completed at workflow level and produced a final `Buy` rating. The upgraded deterministic quality gate marks the run `failed` because the final recommendation did not cite any available `SRC-*` or `RAW-TOOL-*` source IDs and because the pre-synthesis scope audit found unrelated Marvell evidence inside the news report.

The run is therefore useful as an evidence example, not as an acceptable Flint advisory recommendation. It demonstrates the intended workflow behavior: the service can complete a run, capture raw tool provenance, persist artifacts, and then reject the final decision when provenance and scope requirements are not met.

## Run Identity And Top-Level I/O

| Field | Value |
| --- | --- |
| Ticker | `MSFT` |
| Trade date | `2026-04-29` |
| Analyst set | `news` |
| Final parsed rating | `Buy` |
| Current recomputed quality status | `failed` |
| State log bytes | `56939` |
| State log SHA-256 | `6cf4baf984a848d877c83954e675750a126be4943a5d4ab36fe9b55aabee1c4f` |
| Raw provenance bytes | `3271` |
| Raw provenance SHA-256 | `9a0659c908e095c436623094e8a77fba0c47b1a87ba7595d7b4ab4b38` |

Top-level input:

```json
{
  "ticker": "MSFT",
  "trade_date": "2026-04-29",
  "selected_analysts": ["news"]
}
```

Top-level outputs:

| Output | Producer | Consumer |
| --- | --- | --- |
| `news_report` | News Analyst | Research debate, Trader, Risk debate, Portfolio Manager |
| `raw_tool_outputs` | Tool capture node | Portfolio Manager prompt, artifact store, quality audit |
| `source_objects` | Portfolio Manager audit builder | Portfolio Manager prompt, quality audit |
| `recommendation_scorecard` | Portfolio Manager audit builder | Portfolio Manager prompt, quality audit |
| `pre_synthesis_scope_audit` | Portfolio Manager audit builder | Portfolio Manager prompt, quality audit |
| `investment_plan` | Research Manager | Trader, Portfolio Manager |
| `trader_investment_decision` | Trader | Risk debate, state log |
| `risk_debate_state` | Risk analysts | Portfolio Manager, state log |
| `final_trade_decision` | Portfolio Manager | Signal parser, quality audit, memory log, API decision endpoint |

## C4 Context - Information Boundary

```mermaid
C4Context
title MSFT Run - System Context

Person(operator, "Operator", "Queues a shadow run for MSFT on 2026-04-29.")

System_Boundary(shadowBoundary, "tradingagents-flint-shadow") {
  System(api, "Shadow API", "Accepts run creation and exposes status, events, artifacts, and decision.")
  System(worker, "Shadow Worker", "Claims queued run and executes TradingAgents graph.")
  System(graph, "TradingAgentsGraph", "Runs selected analyst, debate, risk, and PM synthesis.")
  System(store, "Repo-local Output Store", "Persists state log, memory log, raw tool JSONL, and manifests.")
}

System_Ext(llm, "Ollama / OpenAI-compatible LLM", "Generates analyst, debate, trader, and PM text.")
System_Ext(vendors, "Data Vendors", "News sources reached through TradingAgents tools.")
System_Ext(flint, "Flint", "Potential downstream reader of advisory artifacts only.")

Rel(operator, api, "POST /v1/shadow-runs", "JSON")
Rel(api, worker, "Queued DB row", "Postgres")
Rel(worker, graph, "run_shadow_job(request)", "Python")
Rel(graph, llm, "Prompt in, model text out", "Chat API")
Rel(graph, vendors, "Tool requests and payloads", "HTTP/API")
Rel(graph, store, "Writes evidence artifacts", "Filesystem")
Rel(flint, store, "Can ingest artifacts later", "Read-only handoff")
```

## C4 Container - Service I/O

```mermaid
C4Container
title MSFT Run - Service Containers And I/O

Person(operator, "Operator", "Uses local UI/API.")

System_Boundary(service, "Shadow Service") {
  Container(api, "FastAPI App", "Python", "Validates create request, records run, returns 202.")
  Container(worker, "Worker Loop", "Python", "Claims queued work and runs graph.")
  ContainerDb(postgres, "Postgres", "Postgres 16", "Stores run status, events, output refs, artifacts.")
  Container(graph, "TradingAgentsGraph", "LangGraph", "Executes analyst/tool/debate/decision pipeline.")
  Container(provenance, "Tool Provenance Capture", "LangGraph node + callback", "Creates RAW-TOOL source records.")
  Container(output, "Output Store", "Filesystem", "Stores JSON state, JSONL provenance, manifest, memory log.")
}

System_Ext(llm, "LLM Provider", "Ollama `llama3.2:latest`.")
System_Ext(news, "News Data Tools", "`get_news`, `get_global_news`.")

Rel(operator, api, "Create run", "JSON")
Rel(api, postgres, "Insert queued run", "SQL")
Rel(worker, postgres, "Claim, transition, persist result", "SQL")
Rel(worker, graph, "Execute request", "Python")
Rel(graph, llm, "Agent prompts and responses", "Chat")
Rel(graph, news, "Tool calls", "Tool API")
Rel(news, provenance, "ToolMessage outputs", "LangGraph state")
Rel(provenance, output, "raw_tool_outputs.jsonl and manifest", "JSONL/JSON")
Rel(graph, output, "full_states_log_2026-04-29.json", "JSON")
Rel(worker, postgres, "Artifact records and quality metadata", "SQL")
```

## C4 Component - Graph I/O

```mermaid
C4Component
title MSFT Run - Graph Components

Container_Boundary(graph, "TradingAgentsGraph") {
  Component(propagator, "Propagator", "Python", "Creates initial AgentState.")
  Component(newsAnalyst, "News Analyst", "LLM node", "Converts tool payloads into `news_report`.")
  Component(newsTools, "tools_news", "ToolNode", "Executes `get_news` and `get_global_news`.")
  Component(capture, "Capture Tools News", "LangGraph node", "Normalizes ToolMessages to RAW-TOOL records.")
  Component(clear, "Msg Clear News", "State cleanup", "Clears tool chatter before debate.")
  Component(research, "Bull/Bear + Research Manager", "LLM nodes", "Creates `investment_plan`.")
  Component(trader, "Trader", "LLM node", "Creates `trader_investment_decision`.")
  Component(risk, "Risk Debate", "LLM nodes", "Creates risk debate histories.")
  Component(pmAudit, "PM Audit Builders", "Deterministic Python", "Creates source objects, scope audit, and six-factor scorecard.")
  Component(pm, "Portfolio Manager", "LLM node", "Creates final decision.")
  Component(signal, "Signal Processor", "Parser", "Parses final rating.")
}

Rel(propagator, newsAnalyst, "AgentState with ticker/date")
Rel(newsAnalyst, newsTools, "Tool calls")
Rel(newsTools, capture, "ToolMessages")
Rel(capture, newsAnalyst, "AgentState + raw_tool_outputs")
Rel(newsAnalyst, clear, "news_report")
Rel(clear, research, "Cleaned messages + reports")
Rel(research, trader, "investment_plan")
Rel(trader, risk, "trader_investment_decision")
Rel(risk, pmAudit, "risk_debate_state + reports")
Rel(pmAudit, pm, "SRC/RAW IDs, scope audit, scorecard")
Rel(pm, signal, "final_trade_decision")
```

## Runtime Sequence

```mermaid
sequenceDiagram
  autonumber
  participant O as Operator
  participant API as FastAPI
  participant DB as Postgres
  participant W as Worker
  participant G as TradingAgentsGraph
  participant N as News Analyst
  participant T as News ToolNode
  participant C as Capture Tools News
  participant L as LLM
  participant PM as Portfolio Manager
  participant S as Output Store
  participant Q as Quality Gate

  O->>API: POST ticker=MSFT, date=2026-04-29, analysts=[news]
  API->>DB: create queued shadow_runs row
  W->>DB: claim run with queued -> running
  W->>G: run_shadow_job(request)
  G->>N: initial AgentState
  N->>L: ask for news analysis or tool calls
  N->>T: request get_news and get_global_news
  T-->>N: ToolMessages
  T-->>C: ToolMessages before clearing
  C-->>G: RAW-TOOL-0001, RAW-TOOL-0002
  N->>L: synthesize news_report
  G->>L: research debate and manager prompts
  G->>L: trader prompt
  G->>L: risk debate prompts
  G->>PM: source objects, raw tool IDs, pre-synthesis scope audit, scorecard
  PM->>L: final decision prompt
  L-->>PM: final_trade_decision
  G->>S: write full state log
  W->>S: write raw tool JSONL and manifest
  W->>Q: assess quality
  Q-->>W: quality_status=failed
  W->>DB: persist output refs, artifacts, quality
```

## Step-by-Step I/O Ledger

| Step | Component | Input | Output | Evidence |
| --- | --- | --- | --- | --- |
| 1 | API create endpoint | `ticker=MSFT`, `trade_date=2026-04-29`, `selected_analysts=[news]` | Queued run row | Service API contract |
| 2 | Worker loop | Queued run | Running event and `run_shadow_job` request | DB event stream |
| 3 | Propagator | Request fields and memory lookup | Initial `AgentState` with empty reports and raw provenance arrays | `tradingagents/graph/propagation.py` |
| 4 | News Analyst | `company_of_interest=MSFT`, `trade_date=2026-04-29`, messages | Tool calls for news retrieval | LangGraph state |
| 5 | `tools_news` | Tool calls | `ToolMessage` results | Raw provenance JSONL |
| 6 | Capture Tools News | ToolMessages | `RAW-TOOL-0001`, `RAW-TOOL-0002` | `raw_tool_outputs.jsonl` |
| 7 | News Analyst | Tool results | `news_report` length 923 bytes/chars in state summary | State log |
| 8 | Message Clear | Report plus message state | Clean state for debate | Graph control flow |
| 9 | Research debate and manager | Reports | `investment_plan` length 2730 | State log |
| 10 | Trader | Investment plan and reports | `trader_investment_decision` length 2488 | State log |
| 11 | Risk debate | Trader plan and reports | `risk_debate_state` histories | State log |
| 12 | PM audit builders | Reports, raw tool outputs, risk state | `source_objects`, `pre_synthesis_scope_audit`, `recommendation_scorecard` | Recomputed current audit |
| 13 | Portfolio Manager | Plans, debate, sources, scope audit, scorecard | `final_trade_decision` length 3071 | State log |
| 14 | Signal Processor | Final decision text | Parsed rating `Buy` | Quality audit |
| 15 | Artifact writer | State, memory, raw provenance | State log, JSONL, manifest, memory log | Output paths |
| 16 | Quality gate | Final decision and final state | `quality_status=failed` | Recomputed quality |

## Raw Tool I/O

| Source ID | Tool | Analyst | Status | Output bytes | Output SHA-256 | Output summary |
| --- | --- | --- | --- | ---:| --- | --- |
| `RAW-TOOL-0001` | `get_news` | `news` | `success` | 341 | `b5eae00e389359b9e9ba7a1ab054cbae5727fd1fa4f9be4126ec3b637e27571c` | MSFT-specific news window from `2026-04-22` to `2026-04-29`; payload included a Qualcomm earnings headline, which is weak evidence for MSFT and illustrates why source-level scrutiny matters. |
| `RAW-TOOL-0002` | `get_global_news` | `news` | `success` | 977 | `b57dda47ed047f001641ee9e2bda1e4723a8afebfabe9190a1f46a5893015ada` | Global market news window from `2026-04-22` to `2026-04-29`; payload included Nasdaq and broader market headlines. |

Raw tool manifest:

```json
{
  "kind": "raw_tool_outputs_manifest",
  "record_count": 2,
  "source_ids": ["RAW-TOOL-0001", "RAW-TOOL-0002"],
  "tools": ["get_global_news", "get_news"],
  "jsonl_sha256": "9a0659c908e095c436623094e8a77fba0c47b1a87ba7595d7b4ab4b38"
}
```

## Agent State I/O

| State field | Producer | Consumer | Observed size / status |
| --- | --- | --- | --- |
| `company_of_interest` | Propagator | All nodes | `MSFT` |
| `trade_date` | Propagator | All nodes | `2026-04-29` |
| `market_report` | Market Analyst | Downstream agents | Empty; market analyst was not selected |
| `sentiment_report` | Social Analyst | Downstream agents | Empty; social analyst was not selected |
| `news_report` | News Analyst | Research, trader, risk, PM | 923 |
| `fundamentals_report` | Fundamentals Analyst | Downstream agents | Empty; fundamentals analyst was not selected |
| `investment_debate_state` | Bull/Bear researchers | Research Manager | Keys: `bear_history`, `bull_history`, `current_response`, `history`, `judge_decision` |
| `investment_plan` | Research Manager | Trader, PM | 2730 |
| `trader_investment_decision` | Trader | Risk debate, state log | 2488 |
| `risk_debate_state` | Risk analysts | PM, state log | Keys: `aggressive_history`, `conservative_history`, `history`, `judge_decision`, `neutral_history` |
| `source_objects` | PM audit builder | PM and quality | 3 |
| `raw_tool_outputs` | Capture Tools News | PM, artifact writer, quality | 2 |
| `recommendation_scorecard` | PM audit builder | PM and quality | Six-factor recomputation available |
| `final_trade_decision` | PM | Signal parser, quality, memory | 3071 |

## Source Object Contract

The final decision had three available source IDs:

| Source ID | Type | Meaning |
| --- | --- | --- |
| `SRC-NEWS-1` | report-level source | News analyst report |
| `RAW-TOOL-0001` | raw tool output | `get_news` result |
| `RAW-TOOL-0002` | raw tool output | `get_global_news` result |

The final decision cited none of them. This is a hard quality failure under the current rigor rules.

## Six-Factor Scorecard

This scorecard is recomputed from the persisted MSFT state using the current upgraded methodology.

| Factor | Available | Source ID | Score | Positive terms | Negative terms |
| --- | --- | --- | ---:| --- | --- |
| `technical_trend` | no | none | 0 | none | none |
| `momentum` | no | none | 0 | none | none |
| `volatility` | no | none | 0 | none | none |
| `news_sentiment` | yes | `SRC-NEWS-1` | 1 | `positive` | none |
| `fundamentals` | no | none | 0 | none | none |
| `risk_posture` | yes | `SRC-RISK-1` | -2 | `balanced`, `diversified` | `risk`, `uncertain`, `volatility`, `conservative` |

Scorecard total: `-1`  
Scorecard suggested rating: `Hold`  
Scorecard suggested direction: `bearish`  
Portfolio Manager final rating: `Buy`  
Reconciliation status: divergent and not explicitly reconciled in the final decision.

## Pre-Synthesis Scope Audit

The upgraded pre-synthesis audit inspects available analyst reports before Portfolio Manager synthesis.

| Audit field | Value |
| --- | --- |
| Requested ticker | `MSFT` |
| Inspected reports | `news_report` |
| Status | `failed` |
| Error | `pre_synthesis_unrelated_entity` |
| Evidence | `marvell (MRVL)` |

Interpretation: the news report contained unrelated issuer evidence. The PM should not treat that evidence as relevant to MSFT. The current quality layer marks this as a hard failure via `pre_synthesis_scope_contamination`.

## Quality Result

Current recomputed quality status: `failed`

| Finding | Severity | Meaning |
| --- | --- | --- |
| `missing_source_object_citation` | error | Final decision did not cite `SRC-NEWS-1`, `RAW-TOOL-0001`, or `RAW-TOOL-0002`. |
| `missing_raw_tool_citation` | error | Raw tool outputs existed but no `RAW-TOOL-*` ID was cited. |
| `no_explicit_source_reference` | warning | Final decision had no explicit source IDs, URLs, or recognized source language. |
| `pre_synthesis_scope_contamination` | error | Pre-PM source audit found unrelated Marvell evidence in the news report. |

## Interpretation

The run completed mechanically, but it should not be consumed by Flint as a valid advisory signal. The evidence chain shows:

- The selected analyst set was narrow: news only.
- The available raw source set was small: two tool outputs.
- The PM produced a `Buy` rating without citing the source IDs it was given.
- The deterministic six-factor scorecard suggested `Hold`, not `Buy`.
- The source audit found unrelated issuer contamination before final synthesis.

The upgraded quality system correctly rejects the result. This is the desired behavior: a run can produce a final recommendation and still be marked unusable when evidence discipline fails.

## Implementation Gap Closure

The following rigor gaps are now closed in code:

| Gap | Current implementation |
| --- | --- |
| Structured tool outputs | `RAW-TOOL-*` objects captured from graph `ToolMessage` outputs before message clearing. |
| Required citations | PM prompt requires `SRC-*` and `RAW-TOOL-*`; quality fails missing/invalid citations. |
| Pre-synthesis ticker/entity validation | PM audit builder creates `pre_synthesis_scope_audit`; quality fails contamination. |
| Six-factor scorecard | Scorecard factors are `technical_trend`, `momentum`, `volatility`, `news_sentiment`, `fundamentals`, `risk_posture`. |
| PM reconciliation | PM prompt requires scorecard reconciliation; quality warns on divergence without reconciliation language. |
| Failed quality on citation or ticker consistency | Citation and ticker/entity issues are severity `error`, producing `quality_status=failed`. |

## Reproduction Commands

Run the relevant test suite:

```bash
.venv/bin/python -m pytest \
  tests/test_tool_provenance.py \
  tests/test_quality_assessment.py \
  tests/test_service_contract.py \
  tests/test_worker_loop.py \
  tests/test_signal_processing.py \
  tests/test_structured_agents.py \
  -q
```

Current verification result: `51 passed`.

Inspect the run artifacts:

```bash
python3 -m json.tool output/logs/MSFT/TradingAgentsStrategy_logs/full_states_log_2026-04-29.json
python3 -m json.tool output/provenance/MSFT/2026-04-29/raw_tool_outputs_manifest.json
sed -n '1,5p' output/provenance/MSFT/2026-04-29/raw_tool_outputs.jsonl
```

## C4InterFlow Note

The C4InterFlow Architecture-as-Code model remains at:

- `Architecture/TradingAgentsFlintShadow.yaml`

Prepared render command:

```bash
C4InterFlow.Cli draw-diagrams \
  --aac-input-paths "./Architecture" \
  --aac-reader-strategy "C4InterFlow.Automation.Readers.YamlAaCReaderStrategy,C4InterFlow.Automation" \
  --interfaces "TradingAgentsFlintShadow.SoftwareSystems.*.Containers.*.Components.*.Interfaces.*" \
  --interfaces "TradingAgentsFlintShadow.SoftwareSystems.*.Containers.*.Interfaces.*" \
  --types c4 c4-static c4-sequence sequence \
  --levels-of-details context container component \
  --formats svg png md \
  --output-dir "./diagrams/tradingagents-flint-shadow"
```

This report embeds Mermaid C4-compatible views for immediate review. The C4InterFlow command is still prepared rather than executed because `C4InterFlow.Cli` is not installed on PATH in this environment.
