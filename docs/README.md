# Documentation Map

Use this file as the index for the `docs/` tree.

## Start Here

- [`graph_flows.md`](./graph_flows.md): shortest current graph overview
- [`graph_execution_reference.md`](./graph_execution_reference.md): code-derived runtime reference
- [`agent_dataflow.md`](./agent_dataflow.md): agent, tool, and memory summary
- [`architecture_learnings.md`](./architecture_learnings.md): practical architecture rules learned from implementation mistakes and refactors

## Architecture and Conventions

- [`agent/context/ARCHITECTURE.md`](./agent/context/ARCHITECTURE.md): internal architecture context
- [`agent/context/CONVENTIONS.md`](./agent/context/CONVENTIONS.md): implementation conventions and default rules
- [`agent/context/COMPONENTS.md`](./agent/context/COMPONENTS.md): component map and code-entry guide
- [`agent/CURRENT_STATE.md`](./agent/CURRENT_STATE.md): active milestone and recent progress

## Portfolio

- [`portfolio/00_overview.md`](./portfolio/00_overview.md): current portfolio architecture
- [`portfolio/02_data_models.md`](./portfolio/02_data_models.md): data models
- [`portfolio/03_database_schema.md`](./portfolio/03_database_schema.md): SQL schema
- [`portfolio/04_repository_api.md`](./portfolio/04_repository_api.md): repository, DB client, and report-store API

## Testing and Evaluations

- [`testing.md`](./testing.md): test strategy, markers, and patterns
- [`FINANCIAL_TOOLS_ANALYSIS.md`](./FINANCIAL_TOOLS_ANALYSIS.md): tool/vendor analysis
- [`finnhub_evaluation.md`](./finnhub_evaluation.md): Finnhub-specific notes

## Historical or Research-Oriented Docs

- [`upstream_pr_review.md`](./upstream_pr_review.md): upstream PR triage notes
- [`agent/decisions/`](./agent/decisions): ADRs and decision records
- [`agent/plans/`](./agent/plans): implementation plans

## Source-of-Truth Guidance

- For current runtime behavior, prefer [`graph_execution_reference.md`](./graph_execution_reference.md).
- For the shortest runtime picture, prefer [`graph_flows.md`](./graph_flows.md).
- For agent roles and memory/tool usage, prefer [`agent_dataflow.md`](./agent_dataflow.md).
- For repo-wide conventions and current operational rules, prefer [`../CLAUDE.md`](../CLAUDE.md).
