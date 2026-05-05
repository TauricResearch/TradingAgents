# Methodology Research Memo

Date: 2026-05-05
Repository: `tradingagents-flint-shadow`

## Summary

The current shadow pipeline is good enough to produce reviewable analyst artifacts, but not good enough to be treated as a commercial-grade trading method.

The main gap is not model size or prompt polish. It is methodology:

- facts are not always separated from claims,
- claims are not always separated from narrative synthesis,
- final decisions are not always tied to source IDs,
- scorecards are still too close to keyword heuristics,
- target user and risk context are under-specified,
- telemetry is not yet rich enough for a serious replay or judge loop.

The right direction is to treat TradingAgents as an evidence-producing advisory system.

## What The Live Evidence Shows

Recent runs show a recurring pattern:

1. The pipeline captures raw tool outputs and structured source objects.
2. The Portfolio Manager can still emit unsupported or weakly supported prose.
3. The quality gate catches some failures after the fact.
4. The evaluation layer labels missing citation discipline as `insufficient_evidence`.

That is useful, but it is a post-hoc defence, not a robust methodology.

## Working Definitions

- `fact`: a raw, source-backed observation with provenance.
- `claim`: an inference made from one or more facts.
- `score`: a deterministic or model-derived metric with a declared method.
- `judgement`: the final evaluation of whether evidence is sufficient for Flint ingestion.

## Policy Position

The system should enforce the following:

1. A final recommendation must cite structured source IDs.
2. Raw tool outputs may be cited when the recommendation depends on them.
3. Narrative prose is not evidence unless it is backed by explicit citations.
4. A recommendation must name its audience and risk profile.
5. A run with missing citations, scope contamination, or failed reconciliation should not be treated as ingestion-ready.
6. Hidden chain-of-thought should not be stored as a durable artifact. Store structured rationale and trace metadata instead.

## Source Policy Questions

These need implementation, not guesswork:

- Which market/news sources are considered primary?
- How many sources are required for a company-specific claim?
- What makes broad market news too weak to support an issuer-specific recommendation?
- How should weekend and holiday trade dates be represented?
- What macro signals are mandatory before a buy case is considered credible?

## Commercial Readiness Criteria

Commercial use requires:

- deterministic run-scoped storage,
- replayable telemetry,
- source-level provenance,
- factor-level scoring,
- explicit investor context,
- judge outputs that can block ingestion,
- licensing clarity for each data source.

## Conclusion

The repo should be hardened as an advisory and audit system first. Only after that should any stronger trading or analyst workflow be considered.
