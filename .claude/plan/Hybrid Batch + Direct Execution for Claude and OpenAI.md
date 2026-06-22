# Hybrid Batch + Direct Execution for Claude and OpenAI

## Summary
Add a provider-neutral hybrid mode: use Batch APIs for wide cheap phases, then switch fragmented/tail phases to normal direct API calls to avoid many async batch turnarounds. Applies to both `anthropic` and `openai`.

## Key Changes
- Add `execution_policy: "batch" | "hybrid-tail"` to batch manifests.
- Keep existing batch adapters for:
  - Anthropic Message Batches
  - OpenAI Batch API
- Add direct LLM clients through existing `create_llm_client(...).get_llm()`:
  - `anthropic`: direct Claude calls
  - `openai`: direct OpenAI Responses/chat calls through current normalized client
- Routing policy:
  - Analyst phases stay batched while tickers are still wide/aligned.
  - Once a ticker completes all selected analysts, run its tail phases direct:
    - Bull/Bear debate
    - Research Manager
    - Trader
    - Risk debate
    - Portfolio Manager
- Add CLI flags:
  ```bash
  batch submit --hybrid-tail
  batch collect RUN_ID --hybrid-tail
  batch wait RUN_ID --hybrid-tail --direct-concurrency 4
  ```
- Add separate accounting:
  - `requests` remains provider-batch request status.
  - `direct_calls` tracks direct call status, node, ticker, model, provider, latency, and errors.

## Provider Behavior
- Anthropic:
  - Batch path keeps 50% discount.
  - Direct tail uses the same Claude quick/deep models already in config.
- OpenAI:
  - Batch path keeps OpenAI Batch discount/async behavior.
  - Direct tail uses the same OpenAI quick/deep models already in config.
- If direct call fails after retries, mark that ticker failed with the node/error; do not corrupt already collected batch results.

## Test Plan
- Fake Anthropic and OpenAI adapters both verify:
  - analyst phase submits provider batches
  - post-analyst phase uses direct calls
  - no extra batch is submitted for debate/risk/portfolio tail
- Manifest compatibility tests:
  - old manifests load as `"batch"`
  - hybrid manifests save/load `direct_calls`
- Mixed-progress test:
  - some tickers still in analysts continue batching
  - tickers already in debate run direct
- CLI tests cover `--hybrid-tail` for submit, collect, and wait.

## Assumptions
- “Quick call” means direct non-batch API call for the same provider.
- Default hybrid cutoff is after all selected analyst reports complete per ticker.
- Default direct concurrency is `4`, configurable by CLI/env.
