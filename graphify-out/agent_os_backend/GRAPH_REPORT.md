# Graph Report - agent_os/backend  (2026-05-04)

## Corpus Check
- Corpus is ~19,625 words - fits in a single context window. You may not need a graph.

## Summary
- 269 nodes · 581 edges · 19 communities detected
- Extraction: 87% EXTRACTED · 13% INFERRED · 0% AMBIGUOUS · INFERRED: 74 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]

## God Nodes (most connected - your core abstractions)
1. `LangGraphEngine` - 39 edges
2. `EventMapper` - 36 edges
3. `MockEngine` - 29 edges
4. `AwaitPhase3Decision` - 23 edges
5. `_persist_run_to_disk()` - 12 edges
6. `_run_and_store()` - 11 edges
7. `_set_run_task()` - 9 edges
8. `_append_scan_rerun_and_store()` - 9 edges
9. `resume_run()` - 9 edges
10. `build_scanner_context_packet()` - 9 edges

## Surprising Connections (you probably didn't know these)
- `Orchestration engine for LangGraph pipeline executions.  This module owns the ru` --uses--> `EventMapper`  [INFERRED]
  agent_os/backend/services/langgraph_engine.py → agent_os/backend/services/event_mapper.py
- `Load a saved market report artifact for pipeline injection.      Supports:     -` --uses--> `EventMapper`  [INFERRED]
  agent_os/backend/services/langgraph_engine.py → agent_os/backend/services/event_mapper.py
- `Raised when auto mode must pause for a user decision before Phase 3.` --uses--> `EventMapper`  [INFERRED]
  agent_os/backend/services/langgraph_engine.py → agent_os/backend/services/event_mapper.py
- `Return the persisted analysts checkpoint payload when analyst output exists.` --uses--> `EventMapper`  [INFERRED]
  agent_os/backend/services/langgraph_engine.py → agent_os/backend/services/event_mapper.py
- `Return the persisted trader checkpoint payload when trader output exists.` --uses--> `EventMapper`  [INFERRED]
  agent_os/backend/services/langgraph_engine.py → agent_os/backend/services/event_mapper.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.12
Nodes (23): AwaitPhase3Decision, Raised when auto mode must pause for a user decision before Phase 3., MockEngine, _ns(), MockEngine — streams scripted events for UI testing without real LLM calls.  Usa, Generates scripted AgentOS events without calling real LLMs., _sleep(), _timestamp() (+15 more)

### Community 1 - "Community 1"
Cohesion: 0.07
Nodes (30): analysis_has_deep_dive(), analysis_is_terminal(), analysis_status(), build_fallback_config(), build_resume_guidance(), fetch_prices(), infer_fallback_tier(), is_fallback_eligible_error() (+22 more)

### Community 2 - "Community 2"
Cohesion: 0.19
Nodes (30): _append_and_store(), _append_scan_rerun_and_store(), _append_system_event(), _build_scan_rerun_state(), _checkpoint_run_events(), _clear_run_task(), _ensure_run_events_loaded(), _filter_rerun_events() (+22 more)

### Community 3 - "Community 3"
Cohesion: 0.12
Nodes (25): _extract_all_messages_content(), _extract_content(), _extract_model(), extract_node_name(), is_root_chain_end(), _map_llm_end(), _map_llm_start(), _map_tool_end() (+17 more)

### Community 4 - "Community 4"
Cohesion: 0.13
Nodes (17): _apply_resume_state(), _build_analysts_checkpoint(), _build_trader_checkpoint(), _build_trading_graph_initial_state(), infer_pipeline_resume_phase(), _load_injected_market_report(), _parse_canonical_regime(), PipelineRecoveryStore (+9 more)

### Community 5 - "Community 5"
Cohesion: 0.19
Nodes (9): _execution_key(), Run the portfolio manager workflow and stream events., Resolve an auto-run Phase 2 pause by retrying selected tickers or continuing., Create and register a ``RunLogger`` for the given canonical run id., Persist the run log to *log_dir*/run_log.jsonl and clean up., Run the 3-phase macro scanner and stream events., Persist scan artifacts and emit system log events., Continue a market scan from *start_node* using a seeded state. (+1 more)

### Community 6 - "Community 6"
Cohesion: 0.16
Nodes (17): _extract_decision_bullets(), extract_pipeline_instruments_from_scan_data(), extract_tickers_from_scan_data(), format_report_section_for_persistence(), _looks_like_prompt_leak(), normalize_scan_summary(), Report and artifact persistence helpers for LangGraphEngine.  Extracted from ``l, Drop obvious prompt/instruction leakage before persisting reports. (+9 more)

### Community 7 - "Community 7"
Cohesion: 0.33
Nodes (15): build_scanner_context_packet(), clean_line(), dedupe_keep_order(), drop_table_header(), extract_ticker_relevant_lines(), _fetch_ground_truth(), format_filtered_earnings_rows(), format_filtered_economic_events() (+7 more)

### Community 8 - "Community 8"
Cohesion: 0.21
Nodes (9): LangGraphEngine, Manually execute a pre-computed PM decision (for resumability)., Run the full auto pipeline: scan → pipeline → portfolio., Load persisted Phase 1 reports into the state shape expected by Phase 2., Continue an auto workflow after re-running part of the market scan., Run or resume the portfolio stage for an auto workflow., Orchestrates LangGraph pipeline executions and streams events., _require_scanner_date() (+1 more)

### Community 9 - "Community 9"
Cohesion: 0.19
Nodes (8): EventMapper, Maps LangGraph v2 events to the AgentOS frontend contract.      One mapper insta, _extract_node_results(), _is_top_level_langgraph_node_end(), Re-run a single ticker's pipeline from a specific phase.          Phases:, Return a compact node-results payload with non-empty values only., Return True for terminal events emitted by top-level LangGraph nodes., Update the rolling pipeline snapshot from a top-level LangGraph node event.

### Community 10 - "Community 10"
Cohesion: 0.2
Nodes (7): _agent_os_already_running(), _hydrate_run_record(), hydrate_runs_from_disk(), lifespan(), Return True when the target port is serving the AgentOS health endpoint., Convert persisted run metadata into an in-memory run record.      A persisted ``, Populate the in-memory runs store from persisted run_meta.json files.

### Community 11 - "Community 11"
Cohesion: 0.43
Nodes (7): get_latest_portfolio_state(), get_portfolio(), get_portfolio_summary(), list_portfolios(), Resolves the 'main_portfolio' alias to the first available portfolio ID., Returns the 'Top 3 Metrics' for the dashboard header., _resolve_portfolio_id()

### Community 12 - "Community 12"
Cohesion: 0.7
Nodes (4): normalize_run_params(), _normalize_ticker(), _normalize_tickers(), Return a canonical params shape for persisted run metadata.

### Community 13 - "Community 13"
Cohesion: 0.67
Nodes (0): 

### Community 14 - "Community 14"
Cohesion: 1.0
Nodes (0): 

### Community 15 - "Community 15"
Cohesion: 1.0
Nodes (0): 

### Community 16 - "Community 16"
Cohesion: 1.0
Nodes (0): 

### Community 17 - "Community 17"
Cohesion: 1.0
Nodes (0): 

### Community 18 - "Community 18"
Cohesion: 1.0
Nodes (0): 

## Knowledge Gaps
- **46 isolated node(s):** `Return a canonical params shape for persisted run metadata.`, `Convert persisted run metadata into an in-memory run record.      A persisted ```, `Populate the in-memory runs store from persisted run_meta.json files.`, `Return True when the target port is serving the AgentOS health endpoint.`, `Resolves the 'main_portfolio' alias to the first available portfolio ID.` (+41 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 14`** (2 nodes): `websocket.py`, `websocket_endpoint()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 15`** (1 nodes): `store.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 16`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 17`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 18`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `EventMapper` connect `Community 9` to `Community 0`, `Community 3`, `Community 4`, `Community 5`, `Community 8`?**
  _High betweenness centrality (0.181) - this node is a cross-community bridge._
- **Why does `LangGraphEngine` connect `Community 8` to `Community 0`, `Community 2`, `Community 4`, `Community 5`, `Community 9`?**
  _High betweenness centrality (0.148) - this node is a cross-community bridge._
- **Why does `MockEngine` connect `Community 0` to `Community 2`?**
  _High betweenness centrality (0.079) - this node is a cross-community bridge._
- **Are the 16 inferred relationships involving `LangGraphEngine` (e.g. with `Mark run failed and append a visible system event with the failure reason.` and `Return the latest completed report per scan node.      Scanner nodes can emit an`) actually correct?**
  _`LangGraphEngine` has 16 INFERRED edges - model-reasoned connections that need verification._
- **Are the 29 inferred relationships involving `EventMapper` (e.g. with `AwaitPhase3Decision` and `PipelineRecoveryStore`) actually correct?**
  _`EventMapper` has 29 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `MockEngine` (e.g. with `Mark run failed and append a visible system event with the failure reason.` and `Return the latest completed report per scan node.      Scanner nodes can emit an`) actually correct?**
  _`MockEngine` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 16 inferred relationships involving `AwaitPhase3Decision` (e.g. with `Mark run failed and append a visible system event with the failure reason.` and `Return the latest completed report per scan node.      Scanner nodes can emit an`) actually correct?**
  _`AwaitPhase3Decision` has 16 INFERRED edges - model-reasoned connections that need verification._