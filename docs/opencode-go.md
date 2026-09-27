# OpenCode Go

Select **OpenCode Go** in the CLI or configure it in `.env`:

```dotenv
OPENCODE_GO_API_KEY=your-go-key
TRADINGAGENTS_LLM_PROVIDER=opencode-go
TRADINGAGENTS_QUICK_THINK_LLM=glm-5.3-flash
TRADINGAGENTS_DEEP_THINK_LLM=kimi-k3
```

No custom base URL, proxy or OpenAI/Anthropic account key is required.
A missing Go key produces an explicit error; another provider's key is never
used as a fallback. The CLI can prompt for and persist the Go key just like
other providers.

## Protocol-aware routing

Go exposes different protocols for different models. The adapter uses the
[official Go endpoint table](https://opencode.ai/docs/go/#endpoints), checked
2026-09-27, rather than sending every model to Chat Completions:

| Protocol | Models | Request path |
| --- | --- | --- |
| Chat Completions | GLM, Kimi, DeepSeek, MiMo, LongCat, Hy and listed free models | `/zen/go/v1/chat/completions` |
| Responses | GPT Luna, Grok and Muse Spark | `/zen/go/v1/responses` |
| Anthropic Messages | MiniMax and Qwen | `/zen/go/v1/messages` |

DeepSeek retains the existing reasoning-content round-trip adapter. Responses
is explicitly enabled for its models, even on Go's non-OpenAI hostname. The
Anthropic SDK receives the correct base without a duplicated `/v1` segment.
Quick and deep models may use different protocols under the same provider.

Use Go's model IDs, e.g. `minimax-m3`, not a direct provider's model catalog.
The `opencode-go/` prefix is also accepted and removed before the API request.
The CLI offers a shortlist plus Custom model ID; the routing table contains
all 34 models listed in the checked endpoint table. Service availability,
account entitlements, regional rules and model features remain provider-side.

For a new/custom model that is not in the routing table, specify its protocol:

```dotenv
TRADINGAGENTS_OPENCODE_GO_API=chat_completions
```

Allowed values: `auto` (default), `chat_completions`, `responses`, `messages`.
An explicit override applies to both configured models; leave it at `auto`
when mixing known models with different protocols. Unknown models in auto
mode fail with guidance rather than guessing an endpoint. Python configuration
uses `opencode_go_api`; direct `create_llm_client` calls use `api`.

A proxy can override `backend_url` / `TRADINGAGENTS_LLM_BACKEND_URL`. Supply an
API base such as `https://proxy.example/custom/v1`, not a complete `/responses`,
`/messages` or `/chat/completions` endpoint. Preserve the Go authentication and
session headers when forwarding.

## Headers and conversation lifetime

Every Go client automatically supplies its own `User-Agent: TradingAgents/<version>`
and a generated `x-opencode-session`. The ID is created once per client, not
once per request, so synchronous/asynchronous calls and SDK retries reuse it.
Deep and quick clients have separate generated IDs. Custom headers override
these defaults case-insensitively and may add other fields; required Go
headers cannot be overridden with empty values.

For a conversation that must resume after a process restart, persist its ID
and supply it explicitly:

```dotenv
TRADINGAGENTS_LLM_HEADERS='{"x-opencode-session":"your-persisted-conversation-id"}'
```

Or in Python before constructing the graph:

```python
config["llm_headers"] = {
    "User-Agent": "MyTradingAgents/1.0",
    "x-opencode-session": persisted_conversation_id,
}
```

A configured header is applied to both deep and quick clients. Automatic IDs
last for the lifetime of the client/graph, not a ticker/date checkpoint: a
long-lived graph reused for independent runs also reuses those IDs. Construct
a fresh graph per independent conversation, or supply a fresh conversation ID
when constructing it. Reuse a persisted ID only for the same conversation;
do not place one permanent ID in `.env` for every unrelated run.

See [custom headers](llm-headers.md) for validation and supported adapters.
Temperature, token caps and retries continue to use the existing settings.
`openai_reasoning_effort` is forwarded only for Go's GPT Responses models;
it is not sent to MiniMax, Qwen or other incompatible models.

## Service scope

[Go's usage requirements](https://opencode.ai/docs/go/#where-can-i-use-it)
currently describe coding-agent traffic. This adapter identifies itself
honestly as TradingAgents; it does not impersonate another client, bypass
usage restrictions or establish official approval for trading-analysis use.
Confirm that your intended use is permitted before sending live workloads.
