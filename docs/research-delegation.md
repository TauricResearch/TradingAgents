# Bounded research delegation

The default graph always carries each available published analyst report
(market, fundamentals, news, sentiment) into the Research Manager as a
separately labelled, bounded evidence lens. It then runs one deterministic,
read-only report-lens task for each non-empty report and appends only those
public findings to the plan consumed by Trader and Portfolio Manager. This
prevents a single Research Manager self-report from being mistaken for
independent confirmation.

The default path is deliberately not a parallel LLM swarm: it makes no extra
model call, does not select tools from model output, and cannot access the
network, execution, or portfolio mutation APIs. It is a safe deterministic
fallback when provider-level parallel research is unavailable or would exceed
the run's model/tool budget.

An embedding application can additionally opt in to up to three independent
factual subquestions during one decision turn. This is a small, explicit
capability, not a general recursive agent runtime.

An embedding application creates a `ResearchDelegationExecutor` with a mapping
of read-only tools, then passes it to `create_research_manager`. The mapping is
the allowlist: a model-requested tool name that is not present is rejected
before execution. Requests run concurrently, retain their request order in the
result, and cannot create further tasks (`parent_depth` must be zero and tool
handlers receive no executor).

Only `public_summary` and source citations are rendered into the investment
plan consumed by Trader and Portfolio Manager. The contract has no fields for
private model reasoning, prompt text, raw provider payloads, or tool traces;
tool exceptions are replaced with a generic failure finding for the same
reason.

```python
from tradingagents.agents.managers.research_manager import create_research_manager
from tradingagents.research.delegation import (
    DelegatedResearchOutput,
    ResearchDelegationExecutor,
)

def filing_lookup(arguments):
    # Implementer enforces its own read-only data access and returns only a
    # presentation-safe evidence summary.
    return DelegatedResearchOutput(
        public_summary="Latest filing reports stable gross margin.",
        citations=("https://disclosure.example/filing",),
    )

executor = ResearchDelegationExecutor({"filing_lookup": filing_lookup}, max_parallel=3)
research_manager = create_research_manager(llm, delegation_executor=executor)
```

Outside `GraphSetup`, `create_research_manager(llm)` remains a backwards-
compatible single-turn manager. The normal graph enables
`use_default_report_lenses=True`; it never advertises the report-lens tool to
the model, so a model cannot select it or turn it into a nested delegation.
Production integrations must supply only read-only tools and must not use this
path to make orders or change portfolio state.
