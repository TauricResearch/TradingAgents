# Custom Ollama Modelfiles for TradingAgents

The main README covers pulling a stock model with `ollama pull <name>` and
selecting **"Custom model ID"** in the CLI. This example goes one step further:
building your own **[Ollama Modelfile](https://github.com/ollama/ollama/blob/main/docs/modelfile.md)**
so the local model is pre-tuned for TradingAgents runs — fixed context length,
quantization, temperature, and generation cap — instead of relying on whatever
defaults the base tag ships with.

Two ready-to-adapt profiles are included, built around a single-GPU (~16GB VRAM)
budget:

| Profile | File | Base | Context | Quant | Best for |
| --- | --- | --- | --- | --- | --- |
| **Fast** | [`Modelfile.trading-fast`](Modelfile.trading-fast) | `qwen3.5:9b-q4_K_M` | 8k | Q4 | Longer prompts, faster turns |
| **Accurate** | [`Modelfile.trading-accurate`](Modelfile.trading-accurate) | `qwen3.5:9b-q8_0` | 4k | Q8 | Best fidelity when prompts fit in 4k |

The trade-off is deliberate: a lighter Q4 quant frees VRAM for a larger 8k
context, while the heavier Q8 quant buys reasoning fidelity at the cost of a
smaller 4k context. Both aim for the same VRAM envelope so you can switch by
name without reconfiguring.

## Why a Modelfile at all?

TradingAgents drives long analyst turns — a system prompt, tool output, and
accumulated debate history all share one context window. Baking the settings
into a Modelfile gives you:

- **Enough context** (`num_ctx`) that analyst turns aren't silently truncated.
- **Low, fixed `temperature`** for the reproducibility the main README
  recommends — reasoning-first hosted models ignore temperature, but local
  models honor it.
- **A `num_predict` cap** so one agent can't run away and stall the graph.
- **`repeat_penalty`** to curb the repetition loops small local models fall
  into on long reports.

## Build

From this directory, with [Ollama](https://ollama.com) installed and running:

```bash
ollama create trading-fast     -f Modelfile.trading-fast
ollama create trading-accurate -f Modelfile.trading-accurate
```

Adjust the `FROM` line to any base model + quant your Ollama library has and
your VRAM fits; the tags above are examples, not requirements.

## Use it in TradingAgents

**Interactive CLI** — choose provider **Ollama**, then at the model prompt pick
**"Custom model ID"** and type `trading-fast` (or `trading-accurate`).

**Programmatic:**

```python
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "ollama"
config["backend_url"] = "http://localhost:11434/v1"  # or your OLLAMA_BASE_URL

# One model for both roles avoids Ollama swapping weights between the quick and
# deep passes on a single GPU — a real speed win on constrained VRAM.
config["quick_think_llm"] = "trading-fast"
config["deep_think_llm"] = "trading-fast"

graph = TradingAgentsGraph(["market", "social", "news", "fundamentals"], config=config)
_, decision = graph.propagate("NVDA", "2026-05-01")
print(decision)
```

**Environment (`.env`)** — for unattended runs, the same choice via env
overrides, which also skip the matching interactive prompts:

```bash
TRADINGAGENTS_LLM_PROVIDER=ollama
TRADINGAGENTS_QUICK_THINK_LLM=trading-fast
TRADINGAGENTS_DEEP_THINK_LLM=trading-fast
# OLLAMA_BASE_URL=http://your-ollama-host:11434/v1   # optional, for a remote server
```

## Tuning notes

- **Out of VRAM?** Lower `num_ctx`, or move to a lighter quant (`q4_K_M` → the
  fast profile already does this).
- **Prompts truncated?** Raise `num_ctx`. Long debate rounds and rich tool
  output are the usual cause.
- **Same model for both roles** on a single GPU: Ollama keeps one set of weights
  resident instead of reloading between the quick and deep passes. Use different
  models only if you have the VRAM headroom for both.
