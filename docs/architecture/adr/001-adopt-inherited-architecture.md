# ADR-001: Adopt the inherited TradingAgents architecture as the baseline

- Status: accepted
- Date: 2026-10-06
- Deciders: the four team members
- Related: D2, CHG-001, ADR-002, D1-REQ-GOV-001

## Context

The brief asks us to enhance an existing prototype — in the course's words, a project "a company
picks up for further modification" — rather than to design a system from nothing. Candidate
upstream is `TauricResearch/TradingAgents` v0.6.0 (Apache-2.0), a multi-agent LLM trading
framework with a broad inherited test suite and a settled public interface. Before writing any
feature code we must decide how much of that inherited architecture to keep.

The inherited system already provides:

- an orchestration graph of analyst, researcher, manager and risk agents (`TradingAgentsGraph`);
- a data layer that isolates vendor libraries and raises typed failures;
- provider-agnostic LLM clients;
- a CLI (`cli.main:app`, console script `tradingagents`);
- persistence under `~/.tradingagents/` driven by `DEFAULT_CONFIG`.

## Decision

Adopt the inherited architecture as the baseline and extend it incrementally. Keep the public
entry points and their contracts unchanged:

- console script `tradingagents` → `cli.main:app`;
- `TradingAgentsGraph(...).propagate(ticker, date)`;
- `DEFAULT_CONFIG`;
- user state under `~/.tradingagents/`.

We will address the system's weaknesses by deliberately modifying existing stages, with each
change carrying its own requirement and evidence, instead of replacing the architecture wholesale.
Later structural changes — notably the move to the `src` layout — are recorded as their own ADRs
(see ADR-002).

## Alternatives considered

### Rewrite from scratch

Rejected. A rewrite discards a working, tested pipeline (1262 passing inherited tests) and the
domain knowledge encoded in its agent stages. The course explicitly frames the task as enhancing an
existing prototype, and a rewrite would spend the whole budget re-attaining behaviour we already
have while producing no auditable comparison against the baseline.

### Freeze upstream and build a parallel system

Rejected. Keeping the inherited code frozen and building an adjacent system would duplicate the
orchestration, data and persistence layers, and would leave two sources of truth for the same
public interface. It also breaks traceability: a fix would live in the parallel system while the
inherited tests keep guarding the frozen one, so neither could be trusted as the product.

### Replace the orchestration framework (LangGraph) with our own

Rejected. The graph framework is load-bearing for the agent workflow and its checkpointing, and
replacing it is a large change on a safety-relevant path with no requirement driving it. If the
orchestration later proves insufficient, that is an architecture change that requires its own ADR,
not a precondition of adopting the baseline.

## Consequences

- Positive: we start from a tested base; every later change is deltas against a known baseline, so
  regressions are detectable by the inherited suite (Gate 5 "prior test suites").
- Positive: the public interface stays stable, so the CLI, tests and downstream scripts keep working.
- Negative: inherited design decisions and technical debt are now ours to own and must be paid down
  deliberately rather than avoided by rewriting.
- Negative: the inherited suite becomes the regression floor, so structural changes must keep every
  inherited test green.

## Reconsider if

- the inherited orchestration cannot express a required behaviour without invasive, unsafe changes;
- the upstream project abandons the licence or diverges in a way that makes incremental alignment
  more expensive than vendoring;
- a requirement appears that the inherited public interface cannot satisfy without a breaking change.
