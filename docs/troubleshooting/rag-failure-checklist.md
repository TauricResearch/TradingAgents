# TradingAgents RAG Failure Checklist

This guide adapts the [WFGY ProblemMap](https://github.com/onestardao/WFGY/blob/main/ProblemMap/README.md) to TradingAgents so contributors can debug multi-agent, retrieval-heavy trading runs in a repeatable way.

## When To Use This Checklist

Use this page when a run looks plausible on the surface but still produces a bad explanation, a bad trade, or inconsistent agent outputs.

Common symptoms:

- Analysts disagree in ways that never get resolved cleanly
- News, sentiment, and fundamentals drift toward different companies or markets
- The final BUY/HOLD/SELL decision is confident but weakly supported
- A backtest result is hard to explain after the fact
- A single bad tool output pollutes the whole downstream chain

## Quick Triage

1. Confirm the exact instrument first. Use the full ticker, including exchange suffixes such as `CNC.TO` or `0700.HK`, before blaming the reasoning layer.
2. Capture the raw inputs. Save the analyst reports, debate histories, and final decision from the same run.
3. Check tool outputs before model outputs. Verify that price, news, and fundamentals all refer to the same instrument and date window.
4. Identify the earliest wrong step. If the market analyst is already off-track, later debate stages are usually downstream fallout.
5. Re-run with a narrower scope if needed. Fewer analysts or fewer debate rounds often make the first failure easier to see.

## 16 Failure Patterns Mapped To TradingAgents

| Problem | TradingAgents symptom | What to inspect first |
| --- | --- | --- |
| 1. Query mismatch | News or fundamentals are about the wrong company | Exact ticker, exchange suffix, tool call arguments |
| 2. Retrieval miss | Reports ignore obvious catalyst news or filings | News date range, provider limits, empty tool responses |
| 3. Long-chain drift | Early analyst mistake compounds into a confident final decision | First analyst report that introduced the wrong premise |
| 4. Context fragmentation | Analysts talk past each other instead of building on shared facts | Per-agent prompts, handoff fields, debate history |
| 5. Over-retrieval | Reports become noisy and contradictory | Too many news items, redundant indicators, low-signal evidence |
| 6. Under-retrieval | Decision looks thin and unsupported | Missing fundamentals, missing macro context, no opposing evidence |
| 7. Memory break | Later stages ignore earlier conclusions or lessons | Stored memories, reflection output, state propagation |
| 8. Black-box debugging | You cannot explain why BUY/HOLD/SELL happened | Saved reports, debate transcripts, final rationale |
| 9. Evidence dilution | Strong evidence is buried under generic commentary | Report structure, ranking of key points, summary quality |
| 10. Tool misuse | Agents call the wrong tool or malformed parameters | Tool descriptions, exact parameter names, raw tool calls |
| 11. Time-window mismatch | Analyst conclusions use different dates or stale data | `trade_date`, look-back windows, cached data files |
| 12. Market mismatch | Symbol collisions across exchanges contaminate the analysis | Exchange-qualified tickers, vendor-specific symbol rules |
| 13. Multi-agent chaos | Debate rounds add noise instead of sharpening a decision | Debate history, max rounds, repeated unsupported arguments |
| 14. Confidence inflation | Model sounds certain even when evidence is weak | Counterarguments, missing caveats, empty or erroring tools |
| 15. Evaluation leakage | Backtest looks good but explanation quality is poor | Whether the same evidence is being reused incorrectly |
| 16. Missing closure | Final report does not prove why the decision is actionable | Final rationale, risk arguments, explicit trade conditions |

## Investigation Workflow

### 1. Verify Instrument Identity

- Confirm the exact ticker used in the CLI or Python entrypoint.
- Prefer exchange-qualified symbols when a root ticker exists on multiple markets.
- Check that the same symbol appears in every analyst report and tool call.

### 2. Verify Data Inputs

- Inspect raw stock data, fundamentals, and news outputs separately.
- Confirm the requested date range and cache contents match the run you are debugging.
- Treat empty tool responses as first-class failures, not minor warnings.

### 3. Inspect Agent Handoffs

- Compare analyst reports with the research debate prompt.
- Check whether the trader is acting on the latest investment plan or a stale premise.
- Check whether the risk debate is responding to the trader's real plan or a generic summary.

### 4. Inspect Decision Quality

- Look for direct evidence behind BUY/HOLD/SELL rather than polished prose.
- Verify that bullish and bearish arguments were both represented.
- If Hold is chosen, make sure it is justified by evidence instead of indecision.

## Evidence To Include In Bug Reports Or PRs

- Exact ticker and date used
- Provider and model configuration
- Which analyst or stage first went wrong
- Raw tool output or screenshots of the relevant report section
- Whether the problem disappears when using an exchange-qualified ticker or fewer debate rounds

## Suggested Fix Patterns

- Tighten prompt wording around exact tickers and exchange suffixes
- Add validation or CLI guidance for ambiguous symbols
- Preserve the exact model id or provider-specific configuration chosen by the user
- Add smaller smoke tests around helper functions and configuration paths before attempting a full end-to-end run
