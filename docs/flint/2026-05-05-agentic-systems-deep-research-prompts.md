# Agentic Systems Deep Research Prompts

Date: 2026-05-05
Repo: `tradingagents-flint-shadow`

Use these as two concurrent deep-research tracks. Keep them independent so they can be run in parallel and later merged into one synthesis memo.

## Shared Brief

We are hardening `TradingAgents` into an evidence-producing advisory system for Flint, not a live trading bot.

Research should focus on state-of-the-art methods that improve:

- source-backed reasoning,
- claim extraction and provenance,
- deterministic scoring and judge layers,
- multi-step agent orchestration,
- replayable telemetry and observability,
- memory and retrieval across runs,
- evaluation and calibration,
- target-profile-aware recommendations.

Prefer methods that can be operationalised in a Python service with local Postgres, file artifacts, and traceable run-scoped storage. Deprioritise toy demos, vague agent buzzwords, and techniques that do not improve evidence quality or auditability.

## Prompt For OpenAI Deep Research

```text
You are researching the current state of the art for evidence-producing agentic systems in financial analysis workflows.

Context:
- The target system is TradingAgents, used as a Flint shadow-analysis sidecar.
- The system must remain advisory only.
- The core goal is to improve methodology: factual provenance, claim graphs, deterministic scoring, judge layers, and replayable traces.
- The current stack already has source IDs, raw tool outputs, a heuristic scorecard, a quality gate, run-scoped artifacts, and structured evaluation storage.

Research questions:
1. What are the strongest current methods for separating facts, claims, and synthesis in agentic systems?
2. What techniques are working best for provenance, citation enforcement, and source traceability?
3. What is the current best practice for deterministic scoring layers that feed an LLM judge rather than being replaced by one?
4. How are frontier teams building evaluator stacks, rubric systems, and “judge over judge” or verifier layers?
5. What observability patterns are used for long-running agent workflows: traces, spans, token usage, prompt hashes, tool-call records, replay, and error taxonomies?
6. What methods are most defensible for target-profile-aware recommendations in finance, especially horizon, benchmark, risk appetite, and portfolio context?
7. What methods exist for memory / retrieval across runs, including embeddings, episodic memory, precedent lookup, and case-based reasoning?
8. What are the current best practices for preventing unsupported recommendations, scope contamination, and prompt injection from news or web content?

Scope:
- Prioritise 2024-2026 papers, product docs, evaluation frameworks, and implementation guides.
- Include production libraries and frameworks where they materially matter: tracing, evals, memory, retrieval, agent orchestration, and provenance.
- Include financial-analysis-specific methods when available, but also general agentic methods that transfer well.

Output format:
- Start with a short executive summary.
- Then provide a table with columns: method, why it matters, evidence/source, weaknesses, implementation fit for this repo.
- Then give a ranked recommendation list for this repository specifically.
- Then list concrete open questions and risks.
- Cite every important claim with direct links.

Important constraints:
- Do not recommend autonomous trading or execution.
- Do not invent benchmarks or claim empirical superiority without evidence.
- When methods conflict, explain the trade-off and which side is more defensible for a Flint shadow-analysis system.
```

## Prompt For Gemini Deep Research

```text
You are researching practical, implementation-oriented methods for building and hardening an agentic financial-analysis system.

Context:
- The target system is TradingAgents, running as a Flint shadow-analysis comparator.
- It already has a graph-based workflow, tool output capture, source IDs, quality gating, evaluation storage, and run-scoped artifacts.
- The missing work is methodology hardening: better scoring, judge logic, source provenance, observability, memory, retrieval, and target-profile-aware recommendations.

Research questions:
1. What agent graph patterns are currently best for auditable multi-step analysis?
2. What prompt, memory, and tool-call patterns reduce hallucination and improve provenance?
3. What retrieval and embeddings patterns are useful for precedent lookup and cross-run memory?
4. What observability architecture is best for traces, spans, artifacts, token accounting, and replay?
5. What eval stack patterns support deterministic gating plus model-based judgment?
6. How should a system like this represent investor profile, horizon, benchmark, and risk appetite in the decision layer?
7. What production patterns exist for storing raw telemetry, source objects, claim graphs, and decision artifacts?
8. What are the main security, data-integrity, and licensing risks in a financial agent workflow?

Scope:
- Prioritise current docs, reference implementations, and practical guides.
- Focus on patterns that can be implemented in Python service code with Postgres, filesystem artifacts, and JSON traces.
- Include source links and concise notes on how each method would map into this repo.

Output format:
- Executive summary.
- “Best-fit architecture options” section with 2-3 architectures and trade-offs.
- “Implementation patterns” section with practical patterns, each with source links and repo mapping notes.
- “Risks and failure modes” section.
- “Recommended next slice” section with the highest-value thing to implement next.

Important constraints:
- Keep the research grounded in evidence, not aspiration.
- Distinguish clearly between proven production practice and speculative ideas.
- Do not recommend live trading or broker integration.
```

## Merge Guidance

After both projects finish, merge into one memo with:

- common patterns,
- conflicts or disagreements,
- methods that are worth implementing immediately,
- methods that should wait for phase 2,
- a short recommendation for Flint-facing integration.
