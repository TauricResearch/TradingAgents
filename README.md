<p align="center">
  <img src="assets/TauricResearch.png" style="width: 60%; height: auto;">
</p>

<div align="center" style="line-height: 1;">
  <a href="https://arxiv.org/abs/2412.20138" target="_blank"><img alt="arXiv" src="https://img.shields.io/badge/arXiv-2412.20138-B31B1B?logo=arxiv"/></a>
  <a href="https://discord.com/invite/hk9PGKShPK" target="_blank"><img alt="Discord" src="https://img.shields.io/badge/Discord-TradingResearch-7289da?logo=discord&logoColor=white&color=7289da"/></a>
  <a href="https://x.com/TauricResearch" target="_blank"><img alt="X Follow" src="https://img.shields.io/badge/X-TauricResearch-white?logo=x&logoColor=white"/></a>
  <a href="https://github.com/TauricResearch/" target="_blank"><img alt="Community" src="https://img.shields.io/badge/GitHub_Community-TauricResearch-14C290?logo=discourse"/></a>
</div>

---

# TradingAgents (Alpaca paper-trading fork)

This repo is a fork of [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents).

**What upstream does:** a team of LLM agents researches one stock and writes a buy/hold/sell memo.

**What this fork adds:** an **Execution Agent** that reads that memo and places an **Alpaca paper trade** — sized as a percent of your **available cash**, not your total portfolio value.

> Research tool only. Not financial advice. See [Tauric disclaimer](https://tauric.ai/disclaimer/).

---

## Quick start

### 1. Clone and install

```bash
git clone https://github.com/Philemon518/TradingAgents.git
cd TradingAgents
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install .
```

### 2. Set up `.env`

```bash
cp .env.example .env
```

Edit `.env` and fill in at least:

| Variable | What it is |
|----------|------------|
| `OPENAI_API_KEY` | Your LLM provider key (or another provider from `.env.example`) |
| `ALPACA_API_KEY` | Alpaca **Key ID** from the dashboard |
| `ALPACA_SECRET_KEY` | Alpaca **Secret Key** (shown once when you generate keys) |

Paper execution is **on by default**. You do not need to set `TRADINGAGENTS_EXECUTION_ENABLED=true` unless you want to be explicit — it is already the default in code and in `.env.example`.

### 3. Get Alpaca paper keys

1. Sign in at [app.alpaca.markets](https://app.alpaca.markets)
2. Switch to **Paper Trading** (upper-left account menu)
3. Open **API Keys** → **Generate New Key**
4. Copy both values immediately:
   - **Key ID** → `ALPACA_API_KEY`
   - **Secret Key** → `ALPACA_SECRET_KEY` (only shown once; regenerate if you lose it)

Keep the paper endpoint:

```bash
ALPACA_BASE_URL=https://paper-api.alpaca.markets
```

### 4. Run

```bash
set -a && source .env && set +a   # load env vars (Windows: use your shell's equivalent)
tradingagents
```

The CLI will ask for a ticker, date, LLM provider, and analysts. A full run takes several minutes.

Alternative:

```bash
python -m cli.main
```

### 5. Read the output

When the run finishes, look for **VI. Execution Agent** in the terminal.

On disk:

```text
reports/<TICKER>_<TIMESTAMP>/6_execution/execution.md
```

---

## Recommendations only (no orders)

To run analysis without sending paper orders:

```bash
TRADINGAGENTS_EXECUTION_ENABLED=false
```

Add that to `.env`, or set it in code:

```python
config = DEFAULT_CONFIG.copy()
config["execution_enabled"] = False
```

You still get buy/hold/sell + cash % in the report; nothing is sent to Alpaca.

---

## How the Execution Agent works

After the Portfolio Manager finishes, the Execution Agent:

1. Reads the Trader + PM write-up (action, entry, stop, target, time horizon, sizing language)
2. Decides **buy / hold / sell**
3. Sizes the order as a **percent of available cash** (Alpaca `cash` field)

**Example:** $10,000 in stocks + $2,000 cash. A 50% buy uses **$1,000** (half of $2,000), not half of $12,000.

**Hold rules while a position is open:**

- Respects the PM **time horizon** (e.g. 3–6 months)
- Sells if price hits the plan's **stop-loss**, even inside the hold window
- After the horizon, a PM **Sell** or stop breach can exit

If the write-up does not mention sizing, the default is **10% of cash** (`TRADINGAGENTS_EXECUTION_FALLBACK_CASH_PCT`).

Shorting is off unless you set `TRADINGAGENTS_EXECUTION_ALLOW_SHORT=true`.

---

## Framework overview

TradingAgents mirrors a trading firm: specialized LLM agents collaborate on one ticker.

<p align="center">
  <img src="assets/schema.png" style="width: 100%; height: auto;">
</p>

| Team | Role |
|------|------|
| **Analysts** | Fundamentals, sentiment, news, technicals |
| **Researchers** | Bull vs bear debate |
| **Trader** | Trade proposal with entry/stop/target |
| **Risk + PM** | Risk review → final buy/hold/sell decision |
| **Execution** *(this fork)* | Paper order on Alpaca |

<p align="center">
  <img src="assets/cli/cli_init.png" width="100%">
</p>

### Supported tickers

Any market Yahoo Finance covers:

- US: `AAPL`, `NVDA`, `SPY`
- International: `0700.HK`, `7203.T`, `RELIANCE.NS`, `600519.SS`
- Crypto: `BTC-USD`, `ETH-USD`

---

## Python usage

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
# config["execution_enabled"] = False   # recommendations only

ta = TradingAgentsGraph(debug=True, config=config)
final_state, decision = ta.propagate("NVDA", "2026-01-15")

print(decision)
print(final_state.get("execution_report"))
```

Change models, debate rounds, etc. in `tradingagents/default_config.py` or via `TRADINGAGENTS_*` env vars (see `.env.example`).

---

## Other setup options

### Docker

```bash
cp .env.example .env
docker compose run --rm tradingagents
```

### More LLM providers

Set the matching key in `.env` — see `.env.example` for the full list (OpenAI, Google, Anthropic, DeepSeek, Groq, Ollama, Bedrock, etc.).

For local models: `llm_provider: "ollama"` with Ollama running at `http://localhost:11434/v1`.

For OpenAI-compatible servers (vLLM, LM Studio): `llm_provider: "openai_compatible"` and set `TRADINGAGENTS_LLM_BACKEND_URL`.

### Checkpoint resume

Resume a crashed run instead of starting over:

```bash
tradingagents --checkpoint
tradingagents --clear-checkpoints    # wipe saved checkpoints first
```

Checkpoints live at `~/.tradingagents/cache/checkpoints/<TICKER>.db`.

---

## Configuration reference

| Setting | Default | Purpose |
|---------|---------|---------|
| `execution_enabled` | `true` | Place Alpaca paper orders |
| `execution_fallback_cash_pct` | `10` | Cash % when write-up has no sizing |
| `alpaca_base_url` | paper API | Do not point at live unless intentional |
| `TRADINGAGENTS_*` | — | Override any config key via env |

Full list: `tradingagents/default_config.py` and `.env.example`.

**Never commit `.env`** — it is gitignored.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for dev setup, tests, and PR guidelines.

---

## Citation

If TradingAgents helps your work, please cite the original paper:

```
@misc{xiao2025tradingagentsmultiagentsllmfinancial,
      title={TradingAgents: Multi-Agents LLM Financial Trading Framework},
      author={Yijia Xiao and Edward Sun and Di Luo and Wei Wang},
      year={2025},
      eprint={2412.20138},
      archivePrefix={arXiv},
      primaryClass={q-fin.TR},
      url={https://arxiv.org/abs/2412.20138},
}
```
