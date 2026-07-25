# Design

Use vertical slices with stable typed artifacts. Data failure must degrade to
provenance-bearing absence, not fabricated content. LLMs may interpret evidence
but deterministic code owns budgets, aggregation, validation, and retention.

The workbench remains a REST/SSE consumer: new backend artifacts travel through
existing snapshot/event/artifact contracts or an additive typed contract. No
private chain-of-thought is saved; structured claims, inputs, tool results,
criteria, decisions, and clamp events are sufficient for audit.

The 13-role convergence path remains mandatory. YAML v1 configures the four
analysts only; downstream roles are fixed until a future graph-safe DAG contract
defines valid bypass semantics.
