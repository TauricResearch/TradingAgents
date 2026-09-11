# Codex plugin foundation: US-001–US-004

Date: 2026-09-11

Status: Design sections approved in conversation; written specification awaiting review. Implementation has not started.

PRD: [TradingAgents Codex plugin and MCP integration](../../../tasks/prd-tradingagents-codex-plugin-mcp.md).
Architecture: [Overall plugin architecture](2026-09-11-codex-plugin-architecture.md).

## Scope and decisions

Deliver one foundation design through four separately verifiable story steps: local MCP runtime, capability discovery, shared analyst prompts, and shared synthesis/reflection logic. Use small extractions in existing role modules. Keep the existing API runner operational throughout.

The user approved this approach over separate runtime/extraction designs or a common role framework. The user also approved the shared-role boundary, runtime boundary, and staged acceptance interpretation described below.

This milestone provides an installed server and reusable role functions. Full analysis execution, public evidence wrappers, SQLite run persistence, report export, reflection jobs, and Codex plugin packaging remain in later stories. Do not create placeholder tools, a generic role framework, or unused workflow/store modules.

## Shared role boundary

Prompt builders live in the existing role modules. They accept existing domain state and explicit output language; sentiment also accepts supplied news, StockTwits, and Reddit blocks. Reflection accepts the existing decision, raw return, alpha return, and benchmark inputs. Keep reflection's existing concise wording and behavior; do not introduce a new reflection-language policy during extraction.

Prompt preparation performs no network requests, model construction, model invocation, or persistence. Reuse the existing instrument-context helper, which reads resolved context from state and has a network-free fallback. Identity lookup remains the caller's responsibility.

Builders return ordinary prompt text or message data appropriate to the existing role. Do not introduce a universal prompt object. LangChain templates, message objects, tool binding, and invocation remain API-adapter concerns; the future plugin can consume shared financial instructions without constructing an API factory.

Preserve financial instructions, date meaning, instrument identity, crypto context, missing-data guidance, and existing role-specific context. Preserve domain wording while moving its construction. Host orchestration instructions may be assembled by adapters, but financial instructions must have one source of truth.

Language handling must stop requiring global configuration inside the shared builders. Adapt the existing language helper to accept an explicit language while preserving its existing no-argument behavior for compatibility. API factories resolve the current configured language and pass it explicitly; plugin callers will pass the frozen run language. English retains the existing empty language instruction.

### US-003: Analysts

Extract builders in `market_analyst.py`, `sentiment_analyst.py`, `news_analyst.py`, and `fundamentals_analyst.py`.

- Market retains its indicator guidance and mandatory verified-snapshot instruction.
- News retains its existing source/tool guidance and date context.
- Fundamentals retains its existing report instructions and crypto context.
- Sentiment consumes the supplied evidence blocks without independently fetching them. Its existing API factory continues fetching all three sources for the same seven-day window before calling the builder. Preserve the deprecated social-media factory alias.

API analyst tool loops retain their existing behavior: tool-call responses are messages, and completed responses populate reports. A prompt extraction must not prematurely treat an intermediate tool call as a finished report.

### US-004: Synthesis and reflection

Extract prompt builders and domain-output update functions for bull, bear, research manager, trader, aggressive/conservative/neutral risk roles, and portfolio manager in their existing modules. Extract the reflection prompt from `graph/reflection.py` so it is callable independently of `Reflector`.

| Role | Context and behavior to preserve |
|---|---|
| Bull and bear | Analyst reports, instrument/crypto context, debate history, explicit absent-opponent marker |
| Research manager | Research debate, instrument context, five-tier recommendation instructions |
| Trader | Research plan, instrument context, optional technical report, absolute numeric price guidance |
| Risk roles | Analyst reports, trader proposal, debate history, other roles' latest responses |
| Portfolio manager | Research plan, trader proposal, risk debate, instrument context, supplied eligible lessons |
| Reflection | Final decision, raw return, benchmark-relative alpha, benchmark name, existing 2–4 sentence instructions |

Shared updates take accepted report text and current domain state, returning the same domain-state patches the factories currently produce. They own report fields, debate prefixes, appended histories, latest responses/speakers, and counters. They do not mutate caller state in place. API adapters add LangChain messages and preserve adapter metadata such as the trader sender.

Structured binding, invocation, renderer use, and free-text fallback remain in API factories. Reuse `SentimentReport`, `ResearchPlan`, `TraderProposal`, `PortfolioDecision`, and their renderers. Shared updates consume rendered text so legacy free-text fallback remains supported. Later plugin stages validate structured submissions before rendering and applying these updates; this milestone does not implement stage validation.

Reflection continues returning text to its existing caller. Do not invent a reflection state updater: outcome calculation, memory updates, historical eligibility, and job persistence remain in US-015–016. Portfolio preparation consumes the supplied `past_context`; it does not independently read memory or decide lesson eligibility.

## Runtime boundary: US-001

Add `tradingagents/plugin/__init__.py` and `server.py`, with a `tradingagents-mcp` entry point in `pyproject.toml`. Use the official Python MCP SDK as an optional `plugin` extra. Base-package installation and imports must remain usable without that SDK; requesting the executable without the extra should give an actionable installation message.

Launch the installed server over local stdio, independently of the repository working directory. The runtime must not instantiate `TradingAgentsGraph`, construct model clients, invoke an API runner, or launch nested agents. Existing base dependencies do not have to be removed to meet this boundary.

Default state root is `~/.tradingagents/plugin/`, with a startup override. Resolve/create the directory and prove it is writable by creating and removing a temporary file. A permission or filesystem error exits unsuccessfully with an actionable stderr message identifying the state-root problem. Do not rely only on permission-bit inspection. Do not create a database before persistent runs require one.

Stdout is exclusively MCP protocol output. Configure logging to stderr and audit startup imports for stdout side effects. Startup does not depend on data credentials and does not make vendor or model requests.

The implementation plan must select and pin an SDK release after verifying its declared compatibility and installation on Python 3.10–3.13. Preserve that matrix; any incompatibility requires a reviewed compatibility decision before implementation proceeds. This design does not assert an unverified SDK version.

## Discovery boundary: US-002

Expose a typed, read-only `get_capabilities` operation. It returns package/runtime and contract-schema versions, role metadata, analysis setting descriptions/defaults, data-source requirements, and credential-presence booleans.

Separate operations actually registered on the server from the financial tools and workflow features planned for subsequent milestones. At this milestone, discovery must not imply that a listed financial capability is callable through MCP merely because its Python implementation exists. Do not register nonfunctional placeholders.

Reuse `ANALYST_NODE_SPECS` for analyst keys, labels, and order, including `social` as the Sentiment Analyst. Keep additional role metadata explicit and small. This is a plugin capability response, separate from the existing LLM-provider capability table.

Describe stock/crypto context, analyst selection, research/risk rounds, language, and vendor selection consistently with the PRD. Mark workflow settings as descriptive until the relevant workflow operations are implemented. Storage paths and credentials are startup configuration, not model-selectable analysis settings.

Inspect only known data credential names supported by existing adapters. Report presence/absence, never raw values, masked values, lengths, or arbitrary environment contents. Presence does not claim credential validity or source availability. Perform no authentication/network probes. Missing optional credentials do not prevent discovery or disable unrelated capabilities.

Identify provider/model/sampling settings as belonging to the existing API runner. They do not configure Codex reasoning and are not plugin prerequisites. Avoid importing runner configuration in a way that lets irrelevant malformed LLM environment overrides break plugin startup.

## Data flow and error ownership

API path: existing caller supplies state → factory obtains evidence where already required and resolves language → shared builder → existing model/tool/structured invocation → existing renderer or fallback text → shared domain update → API message wrapping.

Future plugin path: saved state and evidence plus frozen language → same builder → instructions delivered to Codex → validated/rendered accepted output → same domain update. This future flow establishes the reuse boundary without implementing workflow endpoints now.

Discovery reads metadata and known credential presence only. Startup owns filesystem/dependency failures. API invocation keeps its current fallback/error semantics. Builders do not replace missing evidence with fabricated content or swallow source failures. Future plugin evidence adapters own transport-error versus unavailable-data distinctions.

## Verification and acceptance

Use existing pytest and Ruff infrastructure. No new test framework or type-checking gate.

| Story | Required evidence |
|---|---|
| US-001 | Clean base install without the extra; extra install and executable launch outside checkout; real MCP initialize/list-tools exchange without LLM keys; protocol-only stdout; stderr failure for an unwritable state root |
| US-002 | Capability response/schema checks; registered-versus-planned distinction; credential-present and missing cases; sentinel secrets absent from serialized responses; no network calls or model-client construction |
| US-003 | Builders callable without a model client or fetching; existing factories use extracted content; preserved instrument/date/crypto/language/missing-data instructions; supplied sentiment blocks retained verbatim |
| US-004 | Prompt context checks across synthesis roles; domain patches preserve prefixes/history/counters without input mutation; trader grounding and portfolio lessons preserved; structured fallbacks and reflection messages unchanged |

Reuse and extend relevant existing checks: `test_news_analyst_prompt.py`, `test_crypto_asset_mode.py`, `test_instrument_identity.py`, `test_structured_agent_prompts.py`, `test_structured_agents.py`, `test_debate_opening.py`, `test_analyst_execution.py`, and applicable reflection/memory tests. Add focused shared-builder/update checks where existing tests cannot exercise the extracted boundary. Use supplied outputs and fake models/vendors, never live financial data, for automated compatibility checks.

Guard plugin tests against model-client factory calls. Also exercise direct builders with network access patched to fail so hidden evidence fetching cannot pass unnoticed. For clean-install checks, ensure execution cannot accidentally import the source checkout through the working directory or `PYTHONPATH`.

Run focused checks during implementation, then the full configured suite and `ruff check .` before submission. Preserve Python 3.10–3.13 and the base-install CI checks. Live Codex host acceptance remains US-018.

### Staged acceptance clarification

The user approved demonstrating US-003's plugin reuse in two stages: this milestone proves model-free shared builders and API reuse; actual plugin workflow consumption is verified when the analyst/synthesis stages arrive. Do not mark the complete plugin-consumption criterion passed based only on direct builder tests. Track that remaining integration assertion in the subsequent workflow plan.

Similarly, capability descriptions must state readiness honestly until data and analysis operations ship. Completing US-001–004 does not establish full product parity.

## Delivery and next step

Plan four reviewable steps aligned to US-001, US-002, US-003, and US-004. Runtime/discovery and role extraction remain loosely coupled; no new framework is required to connect them at this stage. Exact helper signatures, startup option spelling, capability field schemas, compatible SDK pin, and test commands belong in the file-level implementation plan, constrained by the decisions above.

After written-spec review, use the writing-plans skill to produce that implementation plan. Do not start implementation as part of this design task.
