# Muse Spark structured-output compatibility

The native OpenCode Go provider supports `muse-spark-1.2-contributor` and
`muse-spark-1.3-contributor` through its Responses endpoint. These models must
not inherit the generic schema-as-function strategy: LangChain forces the
schema's function name with `tool_choice`, while Muse accepts only `auto`.
That caused HTTP 400 followed by the agent's existing free-text fallback.

The shared capability table now selects native `json_schema` structured output
for these Contributor IDs and the standard `muse-spark-1.1`, `muse-spark-1.2`
and `muse-spark-1.3` IDs. LangChain uses `text.format` on Responses and
`response_format` on Chat Completions. No schema tool or forced `tool_choice`
is sent by the default structured-output path. Typed parsing and the ordinary
fallback for genuinely invalid responses remain intact. Unknown model IDs
and other models retain their existing behavior.

This is not a non-interactive-mode bug. Interactive, headless and Python
callers share the same model adapter and structured-output helpers. No change
to the command, model settings, language or headers is needed after updating:

```bash
git pull --ff-only origin main
pip install -e .
tradingagents analyze NVDA --language Chinese
```

## Separate data-source warnings

- A StockTwits HTTP 403 means that source rejected the request. This compatibility
  patch does not bypass its access controls or restore missing StockTwits data.
- `FRED_API_KEY` missing means the optional FRED macro-data source is unavailable.
  Set your own key in the environment or an untracked `.env` to use it. The
  model compatibility patch does not suppress this warning or fabricate data.
- `retrying once as free text` means the structured attempt failed and the
  existing helper is trying plain generation; it does not by itself mean the
  entire run has aborted. The final exit status/report still needs checking.

## Regression tests

```bash
pytest -q tests/test_muse_spark.py
```

The tests verify the capability choices and unchanged strategies for other
models, plus synchronous/asynchronous requests through real LangChain/OpenAI
clients with a fake HTTP transport. The fake endpoint rejects forced tool
choices just like the reported API error, then verifies schema parsing, one
request (no free-text retry), correct endpoint/format and preserved Go headers.
No live service or credentials are required. Install the project's dependencies
to run the transport tests; without `langchain_openai` those tests are skipped.

Sources checked 2026-09-27:

- [Meta tool/function calling](https://dev.meta.ai/docs/cookbook/tool-function-calling):
  only `auto` is supported; forced and disabled tool choices return HTTP 400.
- [Meta structured output](https://dev.meta.ai/docs/cookbook/structured-output):
  use native JSON Schema, including `text.format` on Responses.
- [OpenCode Go endpoints](https://opencode.ai/docs/go/#endpoints):
  Muse Spark Contributor uses `/zen/go/v1/responses`.
