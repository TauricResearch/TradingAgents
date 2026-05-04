# Graph Report - tradingagents  (2026-05-04)

## Corpus Check
- 153 files · ~118,222 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1835 nodes · 3408 edges · 95 communities detected
- Extraction: 69% EXTRACTED · 31% INFERRED · 0% AMBIGUOUS · INFERRED: 1063 edges (avg confidence: 0.5)
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
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 75|Community 75]]
- [[_COMMUNITY_Community 76|Community 76]]
- [[_COMMUNITY_Community 77|Community 77]]
- [[_COMMUNITY_Community 78|Community 78]]
- [[_COMMUNITY_Community 79|Community 79]]
- [[_COMMUNITY_Community 80|Community 80]]
- [[_COMMUNITY_Community 81|Community 81]]
- [[_COMMUNITY_Community 82|Community 82]]
- [[_COMMUNITY_Community 83|Community 83]]
- [[_COMMUNITY_Community 84|Community 84]]
- [[_COMMUNITY_Community 85|Community 85]]
- [[_COMMUNITY_Community 86|Community 86]]
- [[_COMMUNITY_Community 87|Community 87]]
- [[_COMMUNITY_Community 88|Community 88]]
- [[_COMMUNITY_Community 89|Community 89]]
- [[_COMMUNITY_Community 90|Community 90]]
- [[_COMMUNITY_Community 91|Community 91]]
- [[_COMMUNITY_Community 92|Community 92]]
- [[_COMMUNITY_Community 93|Community 93]]
- [[_COMMUNITY_Community 94|Community 94]]

## God Nodes (most connected - your core abstractions)
1. `AgentState` - 75 edges
2. `Portfolio` - 74 edges
3. `Holding` - 74 edges
4. `ReportStore` - 68 edges
5. `PortfolioError` - 53 edges
6. `PortfolioSnapshot` - 52 edges
7. `PortfolioManagerState` - 49 edges
8. `SupabaseClient` - 45 edges
9. `PortfolioRepository` - 45 edges
10. `MongoReportStore` - 42 edges

## Surprising Connections (you probably didn't know these)
- `Summary nodes that compress analyst and debate context for downstream agents.` --uses--> `AgentState`  [INFERRED]
  tradingagents/agents/managers/context_summaries.py → tradingagents/agents/utils/agent_states.py
- `Output validation utilities for detecting hallucinated or off-topic responses.` --uses--> `AgentState`  [INFERRED]
  tradingagents/agents/utils/output_validation.py → tradingagents/agents/utils/agent_states.py
- `Infer a normalized macro regime from explicit pre-fetched macro text only.` --uses--> `AgentState`  [INFERRED]
  tradingagents/agents/utils/output_validation.py → tradingagents/agents/utils/agent_states.py
- `Extract the current/live price from a market analyst report prose.      Patterns` --uses--> `AgentState`  [INFERRED]
  tradingagents/agents/utils/output_validation.py → tradingagents/agents/utils/agent_states.py
- `Build a compact canonical contract for market node output.` --uses--> `AgentState`  [INFERRED]
  tradingagents/agents/utils/output_validation.py → tradingagents/agents/utils/agent_states.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.02
Nodes (143): AgentState, InvestDebateState, RiskDebateState, build_instrument_context(), build_scanner_context_block(), format_prefetched_context(), prefetch_tools_parallel(), Pre-fetch multiple LangChain tools in parallel using ThreadPoolExecutor.      Ea (+135 more)

### Community 1 - "Community 1"
Cohesion: 0.04
Nodes (127): _build_candidate_description(), prioritize_candidates(), Candidate prioritization for the Portfolio Manager.  Scores and ranks scanner-ge, Score and rank candidates by priority_score descending.      Each returned candi, Compute a composite priority score for a single candidate.      Formula::, Concatenate ticker, sector, thesis_angle, rationale, conviction for BM25 query., score_candidate(), get_portfolio_config() (+119 more)

### Community 2 - "Community 2"
Cohesion: 0.03
Nodes (100): Raised when the request times out., ThirdPartyTimeoutError, _fetch_company_news_data(), _format_unix_ts(), get_company_news(), get_insider_transactions(), get_market_news(), Finnhub news and insider transaction functions.  Provides company-specific news, (+92 more)

### Community 3 - "Community 3"
Cohesion: 0.04
Nodes (56): _date_key(), MacroMemory, Macro memory — learn from past regime-level market context.  Stores macro regime, Store a macro regime state for later reflection.          Args:             date, Attach outcome to the most recent macro state for a given date.          Args:, Return most recent macro states, newest first.          Args:             limit:, Build a human-readable context string from recent macro states.          Suitabl, Load all records from the local JSON file. (+48 more)

### Community 4 - "Community 4"
Cohesion: 0.04
Nodes (28): DualReportStore, Dual report store that persists to both local filesystem and MongoDB.  Delegates, Report store that writes to two backends simultaneously.      MongoDB operations, Call *fn* against the Mongo backend; return *default* on any error.          Log, Return the local run-scoped portfolio report directory for *date*., Raised on filesystem read/write failures in ReportStore., ReportStoreError, MongoReportStore (+20 more)

### Community 5 - "Community 5"
Cohesion: 0.05
Nodes (89): AlphaVantageError, APIKeyInvalidError, _default_timeout(), _filter_csv_by_date_range(), format_datetime_for_api(), get_api_key(), _make_api_request(), _rate_limited_request() (+81 more)

### Community 6 - "Community 6"
Cohesion: 0.04
Nodes (66): Exception, APIKeyInvalidError, _default_timeout(), FinnhubError, _fmt_pct(), get_api_key(), _make_api_request(), _now_str() (+58 more)

### Community 7 - "Community 7"
Cohesion: 0.04
Nodes (64): build_final_decision_structured(), build_fundamentals_report_structured(), build_investment_plan_structured(), build_market_report_structured(), build_risk_synthesis_structured(), build_sentiment_report_structured(), build_trader_plan_structured(), canonicalize_source_name() (+56 more)

### Community 8 - "Community 8"
Cohesion: 0.05
Nodes (61): BaseModel, _analysis_has_deep_dive(), _analysis_snapshot(), create_holding_reviewer(), _extract_rating(), _lookup_analysis(), Holding Reviewer LLM agent.  Reviews all open positions in a portfolio and recom, Return True when a ticker analysis contains a completed deep-dive decision. (+53 more)

### Community 9 - "Community 9"
Cohesion: 0.06
Nodes (31): ABC, AnthropicClient, NormalizedChatAnthropic, ChatAnthropic with normalized content output.      Claude models with extended t, Client for Anthropic Claude models., Return configured ChatAnthropic instance., Validate model for Anthropic., BaseLLMClient (+23 more)

### Community 10 - "Community 10"
Cohesion: 0.08
Nodes (10): The canonical run identifier., _load_latest_ts(), Filesystem document store for portfolio and run artifacts.  All artifacts for a, Persist node-level portfolio outputs for a single run., Load the latest node-level portfolio output payload., Filesystem document store for all portfolio-related reports., Return the run-scoped portfolio report directory for *date*., ReportStore (+2 more)

### Community 11 - "Community 11"
Cohesion: 0.06
Nodes (29): _extract_top_sectors(), Parse the sector performance report and return the *top_n* sector keys     ranke, MessagesState, Scanner graph — orchestrates the 4-phase macro scanner pipeline., Create an LLM instance for the given tier.          Mirrors the provider/model/b, Resolve provider-specific kwargs (e.g. thinking_level, reasoning_effort)., Run the scanner pipeline and return the final state.          Args:, Return a compiled partial scanner graph that starts at *start_node*. (+21 more)

### Community 12 - "Community 12"
Cohesion: 0.08
Nodes (43): facts_from_macro_scan_summary(), load_and_parse_macro_scan_summary(), _make_edge(), _make_node(), Adapter: macro_scan_summary.json → partial ScannerGraphFacts dict.  Produces:, Convert a parsed macro_scan_summary.json payload to partial graph facts.      Re, Load and parse macro_scan_summary.json. Fails loudly., _clean_leader() (+35 more)

### Community 13 - "Community 13"
Cohesion: 0.05
Nodes (43): _fetch_finviz_soup(), get_bitcoin_price(), get_breakout_accumulation_stocks(), get_cny_usd_rate(), get_earnings_calendar(), get_economic_calendar(), get_eur_usd_rate(), get_gap_candidates() (+35 more)

### Community 14 - "Community 14"
Cohesion: 0.07
Nodes (28): _add_token_estimate(), estimate_analyze(), estimate_pipeline(), estimate_scan(), format_av_assessment(), format_estimate(), format_vendor_breakdown(), _merge_token_estimate() (+20 more)

### Community 15 - "Community 15"
Cohesion: 0.09
Nodes (21): BaseCallbackHandler, _Event, _extract_graph_node(), _extract_model(), get_run_logger(), _LLMCallbackHandler, Structured observability logging for TradingAgents.  Emits JSON-lines logs captu, Record a tool invocation (called from ``run_tool_loop``). (+13 more)

### Community 16 - "Community 16"
Cohesion: 0.12
Nodes (25): _extract_smart_money_metadata_block(), extract_ticker_sector_from_rotation(), filter_earnings_calendar(), filter_economic_calendar(), filter_factor_alignment_for_ticker(), filter_scanner_context_for_ticker(), filter_smart_money_for_ticker(), _filter_structured_data() (+17 more)

### Community 17 - "Community 17"
Cohesion: 0.16
Nodes (12): circuit_breaker_from_config(), circuit_breaker_state_path(), CircuitBreaker, CircuitBreakerOpen, Small JSON-backed circuit breaker for deterministic agent failures., Raised when a node has exceeded its configured failure threshold., Track recent per-node failures in a stable JSON state file., Raise when *node_name* is open within the rolling window. (+4 more)

### Community 18 - "Community 18"
Cohesion: 0.19
Nodes (19): build_default_config(), _build_env_snapshot(), _dotenv_paths(), _env(), _env_float(), _env_int(), _env_timeout_seconds(), get_env_value() (+11 more)

### Community 19 - "Community 19"
Cohesion: 0.15
Nodes (19): build_debate_evidence_brief(), build_investment_debate_summary(), build_research_packet(), build_risk_debate_summary(), _compact_lines(), _format_fundamentals_structured(), _format_market_structured(), _format_news_structured() (+11 more)

### Community 20 - "Community 20"
Cohesion: 0.13
Nodes (18): _encode_crockford(), generate_run_id(), get_daily_dir(), get_digest_path(), get_eval_dir(), get_market_dir(), get_scanner_graph_facts_path(), get_ticker_dir() (+10 more)

### Community 21 - "Community 21"
Cohesion: 0.12
Nodes (16): get_balance_sheet(), get_cashflow(), get_fundamentals(), get_income_statement(), get_macro_regime(), get_peer_comparison(), get_sector_relative(), get_ttm_analysis() (+8 more)

### Community 22 - "Community 22"
Cohesion: 0.17
Nodes (16): compute_ttm_metrics(), _find_col(), _fmt(), _fmt_pct(), format_ttm_report(), _margin_trend(), _parse_financial_csv(), _pct_change() (+8 more)

### Community 23 - "Community 23"
Cohesion: 0.16
Nodes (9): LessonStore, Returns all lessons, or [] if file is missing., Appends lessons, skipping duplicates. Returns count added., Clears the store (for test isolation)., Append-only JSON store for screening lessons.      Deduplicates on (ticker, scan, build_selection_memory(), load_into_memory(), Convenience: LessonStore + FinancialSituationMemory + load. Used by CLI. (+1 more)

### Community 24 - "Community 24"
Cohesion: 0.2
Nodes (13): build_scanner_graph_facts_from_market_dir(), ensure_scanner_graph_facts(), load_scanner_graph_facts(), _merge_partial_facts(), Builder: merge adapter outputs → validate → save/load immutable artifact.  Immut, Build a complete ScannerGraphFacts dict from a market report directory.      Rai, Write facts to *path* as indented, stably-ordered JSON.      If *path* exists an, Load and return facts from *path*.      Raises:         FileNotFoundError: if fi (+5 more)

### Community 25 - "Community 25"
Cohesion: 0.32
Nodes (13): beta(), check_constraints(), compute_holding_risk(), compute_portfolio_risk(), compute_returns(), max_drawdown(), _mean(), _pvariance() (+5 more)

### Community 26 - "Community 26"
Cohesion: 0.27
Nodes (12): compute_relative_performance(), _fmt_pct(), get_peer_comparison_report(), get_sector_peers(), get_sector_relative_report(), Sector and peer relative performance comparison using yfinance., Identify a ticker's sector and return peer tickers.      Returns:         (secto, Compare ticker's returns vs peers and sector ETF over multiple horizons.      Ar (+4 more)

### Community 27 - "Community 27"
Cohesion: 0.23
Nodes (11): _add_source(), _delete_source(), _find_nlm(), _find_source(), Google NotebookLM sync via the ``nlm`` CLI tool (jacob-bd/notebooklm-mcp-cli)., Add content as a new source., Resolve the path to the nlm CLI., Upload *digest_path* content to Google NotebookLM as a source.      If a source (+3 more)

### Community 28 - "Community 28"
Cohesion: 0.27
Nodes (11): _coerce_json_payload(), _dedupe_feed(), get_global_news(), get_insider_transactions(), get_news(), Returns global market news & sentiment data without ticker-specific filtering., Returns latest and historical insider transactions by key stakeholders.      Cov, Returns live and historical market news & sentiment data from premier news outle (+3 more)

### Community 29 - "Community 29"
Cohesion: 0.24
Nodes (11): compute_risk_metrics(), _daily_returns(), _mean(), _percentile(), Pure-Python risk metrics computation for the Portfolio Manager.  This module com, Return the *pct*-th percentile of *values* using linear interpolation.      Args, Compute portfolio risk metrics from a NAV time series.      Args:         snapsh, Compute daily percentage returns from an ordered NAV series.      Returns a list (+3 more)

### Community 30 - "Community 30"
Cohesion: 0.27
Nodes (6): _build_candidate_rankings(), _extract_rankable_tickers(), _fallback_candidate_from_ranking(), _normalize_candidate_item(), _parse_gatekeeper_rows(), _repair_macro_summary()

### Community 31 - "Community 31"
Cohesion: 0.25
Nodes (10): fetch_news_summary(), fetch_price_trend(), generate_lesson(), load_scan_candidates(), Fetch n headlines, weighted toward largest-move dates.     Strategy: 2 headlines, Read macro_scan_summary.md for scan_date, extract stocks_to_investigate.     Fal, Invoke quick_think LLM, parse JSON via extract_json(), return lesson dict.     R, Top-level: load candidates, fetch data, generate lessons, return list. (+2 more)

### Community 32 - "Community 32"
Cohesion: 0.29
Nodes (8): CanonicalInstrument, instrument_metadata(), is_equity_pipeline_supported(), normalize_symbol(), Canonical instrument identity and classification helpers.  The current system on, Return True for instruments allowed into the current stock deep-dive path., Return the canonical uppercase symbol while preserving suffixes., resolve_instrument()

### Community 33 - "Community 33"
Cohesion: 0.27
Nodes (9): _dedup_edges(), get_render_tool(), Prompt renderer for scanner_graph_facts artifacts.  Converts a ticker's 2-hop su, Return a LangChain @tool that renders ticker graph context from state (scan_date, Keep one edge per (source, relation, target); prefer highest confidence., Render prompt-ready ticker graph context.      Args:         facts:       Scanne, _render_edge_line(), _render_node_line() (+1 more)

### Community 34 - "Community 34"
Cohesion: 0.27
Nodes (9): AbortSignal, GlobalRegime, GraphEdge, GraphNode, Canonical schema contract for scanner_graph_facts.v1., Return a list of validation error strings. Empty list = valid., ScannerGraphFacts, validate_graph_facts() (+1 more)

### Community 35 - "Community 35"
Cohesion: 0.24
Nodes (9): assess_report_quality(), format_quality_header(), parse_quality_header(), Deterministic report quality assessment for scanner node outputs.  Pure function, Format an inline quality header from an assessment dict.      Example outputs:, Assess a scanner report and prepend an inline quality header.      Convenience w, Parse an inline [QUALITY: ...] header from report text.      Returns None if no, Assess the quality of a scanner node report.      Returns a dict with:         q (+1 more)

### Community 36 - "Community 36"
Cohesion: 0.29
Nodes (9): _base_config(), get_config(), initialize_config(), Initialize runtime config once from DEFAULT_CONFIG., Merge a caller-provided config onto a fresh default baseline., Reset runtime config to defaults.      Args:         load_dotenv:             -, Return an isolated copy of current runtime config., reset_config() (+1 more)

### Community 37 - "Community 37"
Cohesion: 0.31
Nodes (8): _build_from_markdown_only(), _has_usable_markdown(), _main(), Historical rebuild utility for scanner_graph_facts.json artifacts.  This is the, Return True if at least one non-quality-gated *_summary.md exists., Build facts from Markdown summaries only (degraded fallback: macro JSON malforme, Rebuild the scanner_graph_facts.json artifact for the given scan_date + run_id., rebuild_scanner_graph_facts()

### Community 38 - "Community 38"
Cohesion: 0.22
Nodes (8): get_global_news(), get_insider_transactions(), get_news(), get_social_sentiment(), Retrieve news data for a given ticker symbol.     Uses the configured news_data, Retrieve global news data.     Uses the configured news_data vendor.     Args:, Retrieve headline-level sentiment signals for a given ticker symbol.     Extract, Retrieve insider transaction information about a company.     Uses the configure

### Community 39 - "Community 39"
Cohesion: 0.22
Nodes (8): get_balance_sheet(), get_cashflow(), get_fundamentals(), get_income_statement(), Retrieve balance sheet data for a given ticker symbol using Alpha Vantage., Retrieve cash flow statement data for a given ticker symbol using Alpha Vantage., Retrieve comprehensive fundamental data for a given ticker symbol using Alpha Va, Retrieve income statement data for a given ticker symbol using Alpha Vantage.

### Community 40 - "Community 40"
Cohesion: 0.25
Nodes (7): assert_regime_consistent(), get_provider_kwargs(), Shared graph utilities used by TradingAgentsGraph, ScannerGraph, and PortfolioGr, Resolve provider-specific LLM kwargs for the given tier.      Args:         conf, Visualize a compiled LangGraph in various formats.      Args:         graph: A c, Compare regime label/score in analyst output against the canonical brief.      R, visualize_graph()

### Community 41 - "Community 41"
Cohesion: 0.29
Nodes (7): check_claims_via_llm(), extract_rm_claims(), _parse_and_validate(), RM consistency guard: structural claim extraction + LLM-as-judge verification., Parse raw LLM output and validate schema. Raises ValueError on any problem., Verdict each claim against fundamentals via a single LLM call with one schema re, Return claim strings from [HIGH]/[MED]/[LOW] bullet lines in RM investment plan.

### Community 42 - "Community 42"
Cohesion: 0.29
Nodes (7): aliases_for_node(), Curated alias registry for scanner graph facts.  This is a living file. When a n, Return curated aliases for a canonical node id/type., Resolve *label* through the curated registry for one node type., Return the canonical key for *label*, or None if not found.      Checks both the, resolve_alias(), resolve_alias_for_type()

### Community 43 - "Community 43"
Cohesion: 0.32
Nodes (6): bind_max_tokens_if_supported(), invoke_with_timeout(), _is_retryable_error(), Return the effective LLM timeout (seconds) for a given reasoning tier.      Read, Return True for transient LLM API errors worth retrying.      Provider-agnostic:, resolve_timeout()

### Community 44 - "Community 44"
Cohesion: 0.29
Nodes (4): _build_market_prompt(), _canonical_regime_text(), _compact_timeseries_text(), Keep prompt-safe slices of large CSV/indicator blocks.

### Community 45 - "Community 45"
Cohesion: 0.32
Nodes (7): _coerce_float(), _coerce_int(), get_rate_limiter(), Tier-keyed process-wide LLM rate limiters.  Buckets are keyed by *tier* (``quick, Drop all cached limiters. Tests use this between cases., Return a process-wide rate limiter for *tier*, or None if unconfigured.      Laz, reset_rate_limiters()

### Community 46 - "Community 46"
Cohesion: 0.29
Nodes (1): Summary nodes that compress analyst and debate context for downstream agents.

### Community 47 - "Community 47"
Cohesion: 0.62
Nodes (6): _format_price_table(), get_bitcoin_price_alpha_vantage(), get_gold_price_alpha_vantage(), get_oil_prices_alpha_vantage(), _parse_json(), _parse_oil_row()

### Community 48 - "Community 48"
Cohesion: 0.33
Nodes (6): buy_order_guard(), _is_cash_sweep(), Shared executable buy-order guards.  Single source of truth for order-level cons, Return the live execution price for a buy order.      For cash-sweep SGOV orders, Return a rejection reason string when the buy violates order guards.      Return, resolve_buy_execution_price()

### Community 49 - "Community 49"
Cohesion: 0.4
Nodes (5): _find_seed_node(), JSON graph search: exact/alias ticker lookup + 1–3-hop undirected subgraph retri, Return the node dict whose id or aliases match *query* (case-insensitive for id), Return the *hops*-hop undirected subgraph seeded on *ticker*.      Args:, retrieve_ticker_subgraph()

### Community 50 - "Community 50"
Cohesion: 0.4
Nodes (5): extract_json(), Robust JSON extraction from LLM responses that may wrap JSON in markdown or pros, Robustly strip <think>, <thinking>, or <thought> blocks from LLM output.      Us, Extract a JSON object from LLM output that may contain markdown fences,     prea, sanitize_llm_output()

### Community 51 - "Community 51"
Cohesion: 0.4
Nodes (4): check_vendor_health(), Cheap vendor health/configuration checks for operator-visible preflight., Return structured degradation warnings without raising.      The default check i, _warning()

### Community 52 - "Community 52"
Cohesion: 0.6
Nodes (3): _extract_current_price_from_state(), _extract_entry_price_from_plan(), _parse_price_token()

### Community 53 - "Community 53"
Cohesion: 0.4
Nodes (0): 

### Community 54 - "Community 54"
Cohesion: 0.5
Nodes (3): append_to_digest(), Daily digest consolidation.  Appends individual report entries (analyze or scan), Append a timestamped section to the daily digest file.      Parameters     -----

### Community 55 - "Community 55"
Cohesion: 0.5
Nodes (2): Central rulesets for all prompt-compression summary nodes., SummaryRuleSet

### Community 56 - "Community 56"
Cohesion: 0.5
Nodes (3): anonymize_ticker(), Ticker anonymization for debate prompts., Replace all occurrences of *ticker* (case-insensitive) with *alias*.      Also h

### Community 57 - "Community 57"
Cohesion: 0.5
Nodes (3): Utility for running an LLM tool-calling loop within a single graph node.  The ex, Invoke *chain* in a loop, executing any tool calls until the LLM     produces a, run_tool_loop()

### Community 58 - "Community 58"
Cohesion: 0.5
Nodes (2): raise_abort(), Build a partial state update that signals a structured graph abort.

### Community 59 - "Community 59"
Cohesion: 0.5
Nodes (3): get_gap_candidates_finviz(), Finviz vendor implementations for scanner data methods., Fetch gap-up candidates using Finviz native gap filter (exact, not approximated)

### Community 60 - "Community 60"
Cohesion: 0.5
Nodes (3): Model name validators for each provider.  Only validates model names - does NOT, Check if model name is valid for the given provider.      For ollama, openrouter, validate_model()

### Community 61 - "Community 61"
Cohesion: 0.67
Nodes (2): get_stock_data(), Retrieve stock price data (OHLCV) for a given ticker symbol.     Uses the config

### Community 62 - "Community 62"
Cohesion: 0.67
Nodes (2): get_indicators(), Retrieve a single technical indicator for a given ticker symbol.     Uses the co

### Community 63 - "Community 63"
Cohesion: 0.67
Nodes (2): get_stock(), Returns raw daily OHLCV values, adjusted close values, and historical split/divi

### Community 64 - "Community 64"
Cohesion: 1.0
Nodes (0): 

### Community 65 - "Community 65"
Cohesion: 1.0
Nodes (0): 

### Community 66 - "Community 66"
Cohesion: 1.0
Nodes (0): 

### Community 67 - "Community 67"
Cohesion: 1.0
Nodes (0): 

### Community 68 - "Community 68"
Cohesion: 1.0
Nodes (0): 

### Community 69 - "Community 69"
Cohesion: 1.0
Nodes (0): 

### Community 70 - "Community 70"
Cohesion: 1.0
Nodes (0): 

### Community 71 - "Community 71"
Cohesion: 1.0
Nodes (0): 

### Community 72 - "Community 72"
Cohesion: 1.0
Nodes (0): 

### Community 73 - "Community 73"
Cohesion: 1.0
Nodes (0): 

### Community 74 - "Community 74"
Cohesion: 1.0
Nodes (0): 

### Community 75 - "Community 75"
Cohesion: 1.0
Nodes (0): 

### Community 76 - "Community 76"
Cohesion: 1.0
Nodes (0): 

### Community 77 - "Community 77"
Cohesion: 1.0
Nodes (0): 

### Community 78 - "Community 78"
Cohesion: 1.0
Nodes (0): 

### Community 79 - "Community 79"
Cohesion: 1.0
Nodes (0): 

### Community 80 - "Community 80"
Cohesion: 1.0
Nodes (0): 

### Community 81 - "Community 81"
Cohesion: 1.0
Nodes (0): 

### Community 82 - "Community 82"
Cohesion: 1.0
Nodes (0): 

### Community 83 - "Community 83"
Cohesion: 1.0
Nodes (0): 

### Community 84 - "Community 84"
Cohesion: 1.0
Nodes (0): 

### Community 85 - "Community 85"
Cohesion: 1.0
Nodes (0): 

### Community 86 - "Community 86"
Cohesion: 1.0
Nodes (0): 

### Community 87 - "Community 87"
Cohesion: 1.0
Nodes (0): 

### Community 88 - "Community 88"
Cohesion: 1.0
Nodes (1): Deserialise from a DB row or JSON dict.          Missing optional fields default

### Community 89 - "Community 89"
Cohesion: 1.0
Nodes (1): Deserialise from a DB row or JSON dict.

### Community 90 - "Community 90"
Cohesion: 1.0
Nodes (1): Deserialise from a DB row or JSON dict.

### Community 91 - "Community 91"
Cohesion: 1.0
Nodes (1): Deserialise from DB row or JSON dict.          ``holdings_snapshot`` is parsed f

### Community 92 - "Community 92"
Cohesion: 1.0
Nodes (1): Return the configured LLM instance.

### Community 93 - "Community 93"
Cohesion: 1.0
Nodes (1): Validate that the model is supported by this client.

### Community 94 - "Community 94"
Cohesion: 1.0
Nodes (0): 

## Knowledge Gaps
- **328 isolated node(s):** `Structured observability logging for TradingAgents.  Emits JSON-lines logs captu`, `Accumulates structured events for a single run (analyze / scan / pipeline).`, `Record a data-vendor call (called from ``route_to_vendor``).`, `Record a tool invocation (called from ``run_tool_loop``).`, `Record that a report file was written.` (+323 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 64`** (2 nodes): `create_bull_researcher()`, `bull_researcher.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 65`** (2 nodes): `create_bear_researcher()`, `bear_researcher.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 66`** (2 nodes): `create_conservative_debator()`, `conservative_debator.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 67`** (2 nodes): `create_aggressive_debator()`, `aggressive_debator.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 68`** (2 nodes): `create_neutral_debator()`, `neutral_debator.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 69`** (2 nodes): `create_portfolio_manager()`, `portfolio_manager.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 70`** (2 nodes): `create_critical_abort_terminal()`, `critical_abort_terminal.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 71`** (2 nodes): `create_research_manager()`, `research_manager.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 72`** (2 nodes): `create_social_media_analyst()`, `social_media_analyst.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 73`** (2 nodes): `create_fundamentals_analyst()`, `fundamentals_analyst.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 74`** (2 nodes): `create_market_movers_scanner()`, `market_movers_scanner.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 75`** (2 nodes): `create_gatekeeper_scanner()`, `gatekeeper_scanner.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 76`** (2 nodes): `create_factor_alignment_scanner()`, `factor_alignment_scanner.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 77`** (2 nodes): `create_geopolitical_scanner()`, `geopolitical_scanner.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 78`** (2 nodes): `create_drift_scanner()`, `drift_scanner.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 79`** (2 nodes): `create_sector_scanner()`, `sector_scanner.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 80`** (1 nodes): `constants.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 81`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 82`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 83`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 84`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 85`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 86`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 87`** (1 nodes): `alpha_vantage.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 88`** (1 nodes): `Deserialise from a DB row or JSON dict.          Missing optional fields default`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 89`** (1 nodes): `Deserialise from a DB row or JSON dict.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 90`** (1 nodes): `Deserialise from a DB row or JSON dict.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 91`** (1 nodes): `Deserialise from DB row or JSON dict.          ``holdings_snapshot`` is parsed f`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 92`** (1 nodes): `Return the configured LLM instance.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 93`** (1 nodes): `Validate that the model is supported by this client.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 94`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `AgentState` connect `Community 0` to `Community 1`, `Community 6`, `Community 7`, `Community 11`, `Community 44`, `Community 46`, `Community 19`, `Community 58`?**
  _High betweenness centrality (0.134) - this node is a cross-community bridge._
- **Why does `CandidateHandoffError` connect `Community 1` to `Community 0`, `Community 3`, `Community 6`, `Community 7`?**
  _High betweenness centrality (0.096) - this node is a cross-community bridge._
- **Why does `PortfolioError` connect `Community 1` to `Community 4`, `Community 6`?**
  _High betweenness centrality (0.083) - this node is a cross-community bridge._
- **Are the 73 inferred relationships involving `AgentState` (e.g. with `ConditionalLogic` and `Handles conditional logic for determining graph flow.`) actually correct?**
  _`AgentState` has 73 INFERRED edges - model-reasoned connections that need verification._
- **Are the 70 inferred relationships involving `Portfolio` (e.g. with `PortfolioGraphSetup` and `Portfolio Manager workflow graph setup.  Fan-out/fan-in workflow:   START → load`) actually correct?**
  _`Portfolio` has 70 INFERRED edges - model-reasoned connections that need verification._
- **Are the 70 inferred relationships involving `Holding` (e.g. with `PortfolioGraphSetup` and `Portfolio Manager workflow graph setup.  Fan-out/fan-in workflow:   START → load`) actually correct?**
  _`Holding` has 70 INFERRED edges - model-reasoned connections that need verification._
- **Are the 30 inferred relationships involving `ReportStore` (e.g. with `LangChain tools that expose Portfolio Manager data to agents.  These tools wrap` and `Enrich portfolio holdings with current prices to compute P&L and weights.      U`) actually correct?**
  _`ReportStore` has 30 INFERRED edges - model-reasoned connections that need verification._