# Setup guide: the web UI with your own portfolio

Getting from a clone to an analysis of your actual holdings, in the browser.
The [README](README.md) is the reference for the whole project; this is the
path through it.

Before anything else: TradingAgents is a research scaffold for studying
multi-agent analysis. Its output is not financial advice, and a rating it
produces is an argument to read, not a trade to place.

---

## 1. Install

Python 3.11 or later. From a clone of the repository:

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install ".[webui]"
```

The `webui` extra adds FastAPI and uvicorn. Without it you get the CLI only,
and `tradingagents ui` will tell you what to install.

Check it took:

```bash
tradingagents --help
```

## 2. Point it at a model

Every run calls a language model, so one provider must be configured. Copy the
template and fill in the one you use:

```bash
cp .env.example .env
```

### DigitalOcean Gradient serverless inference

One endpoint and one key reach models from several vendors. In the DigitalOcean
control panel, click **INFERENCE** in the left menu, then **Manage**, then
**Create model access key**. A DigitalOcean personal access token works in its
place. Then in `.env`:

```bash
DIGITALOCEAN_MODEL_ACCESS_KEY=your-key
TRADINGAGENTS_LLM_PROVIDER=digitalocean
TRADINGAGENTS_DEEP_THINK_LLM=anthropic-claude-opus-5.5
TRADINGAGENTS_QUICK_THINK_LLM=anthropic-claude-haiku-4.5
```

Model IDs are DigitalOcean's, namespaced by vendor: `anthropic-claude-opus-5.5`,
not Anthropic's own `claude-opus-5-5`. The picker lists the models worth running
this pipeline on; anything else DigitalOcean serves works through "Custom model
ID", and no model ID is rejected.

Two models are configured because the pipeline uses two. The **deep** model runs
the debates and the final decision; the **quick** model runs the analysts and
tool loops, which are far more numerous. Pairing a strong deep model with a
cheap quick one is most of the cost control available to you.

### Another provider

Set that provider's key and name it. Anything in
[`.env.example`](.env.example) works:

```bash
OPENAI_API_KEY=...                      # or ANTHROPIC_API_KEY, GOOGLE_API_KEY, ...
TRADINGAGENTS_LLM_PROVIDER=openai
TRADINGAGENTS_DEEP_THINK_LLM=gpt-6-sol
TRADINGAGENTS_QUICK_THINK_LLM=gpt-6-luna
```

### Optional data keys

The pipeline runs without these; each one widens what the analysts can see.

| Variable | What it adds | Cost |
|---|---|---|
| `FRED_API_KEY` | Federal Reserve macro series | free |
| `ALPHA_VANTAGE_API_KEY` | an alternative price and news vendor | free tier |
| `SEC_EDGAR_USER_AGENT` | a contact address SEC can reach you at | none; no key |
| `TYPESAFE_API_KEY` | screens social posts before the Sentiment Analyst reads them | paid |

Set `SEC_EDGAR_USER_AGENT="Your Name your@email.com"` if you analyze US equities
with any regularity — SEC asks callers to identify themselves, and the default
contact points at the project rather than at you.

## 3. Start the UI

```bash
tradingagents ui
```

It serves `http://localhost:8000` and opens a browser. `--port` moves it,
`--no-open` leaves the browser alone.

**It has no authentication.** It holds your positions and spends your provider
key, so it binds to loopback only. For access from another machine, tunnel to it
rather than binding wide:

```bash
ssh -L 8000:localhost:8000 your-host
```

Binding elsewhere (`--host 0.0.0.0`, which a container needs) prints a warning
and proceeds.

## 4. Load your portfolio

Without a book the agents write guidance for a reader who applies it to their
own position. With one, the trader, the risk analysts and the portfolio manager
size against what you actually hold — the difference between "NVDA looks strong"
and "you already hold 120 of these, don't add".

### From a broker CSV

Find the export or download link on your broker's positions page — Schwab puts
it above the positions table on **Accounts → Positions**, and Fidelity and
Vanguard have the equivalent on their positions and holdings pages. Brokers move
these, so go by the page rather than the exact path. Any CSV with a header row
naming a symbol column and a quantity column will parse.

Drop the file on the Portfolio tab. The file is read by the server on your own
machine; nothing is uploaded anywhere.

What the importer does, and why:

- **Average price comes from the cost basis, not the market price**, so the
  agents see what you paid rather than what it is worth today.
- **A symbol held in two accounts becomes one position** at a blended cost, and
  every account's cash row adds to one cash figure. The pipeline reasons about
  one book.
- **A slashed share class is converted** — Schwab's `BRK/B` is `BRK-B` to the
  data layer that prices it. A dotted suffix is left alone, because that is also
  how exchanges are written and `7203.T` is a real Tokyo symbol.
- **What it cannot import, it names.** Options contracts (the data layer prices
  equities and crypto, not contracts) and rows with no readable quantity are
  listed rather than dropped quietly.
- **A withheld cost basis leaves the average price empty**, which the agents
  read as a holding with no entry price — not as an entry price of zero.

An import is a **preview**. It fills the form and waits for **Save book**, so a
misread column cannot overwrite something you typed. Check the rows, then save.

### By hand

Add rows directly. Ticker and quantity are required; average price is optional.
A negative quantity is a short.

### Three states, not two

| What you do | What the agents are told |
|---|---|
| No book saved | nothing about your position — advice is written for a general reader |
| Book saved with no positions | you are **flat**, deliberately |
| Book saved with positions | exactly what you hold |

Deleting the book — not emptying it — is how you go back to un-situated advice.

The saved file is the same JSON the CLI's `--portfolio` takes, at
`~/.tradingagents/portfolio.json`, so a book entered in the browser runs from a
script unchanged:

```bash
tradingagents --portfolio ~/.tradingagents/portfolio.json --ticker NVDA
```

Set `TRADINGAGENTS_PORTFOLIO_PATH` to keep it somewhere else.

## 5. Run an analysis

On the Analyze tab, enter a ticker and press **Analyze ticker**.

- **Ticker** — any symbol Yahoo Finance covers, with its exchange suffix:
  `AAPL`, `0700.HK`, `7203.T`, `RELIANCE.NS`, `BTC-USD`.
- **Analysis date** — defaults to today and cannot be in the future. An earlier
  date serves data as it stood that day, so a backtest cannot see ahead.
- **Analysts** — fewer is faster and cheaper. A crypto ticker drops the
  fundamentals analyst, which has no filings to read.
- **Rounds** — how long the debates run. Start at 1.

**Analyze every holding** queues one run per position. Runs execute **one at a
time**: each costs real money at your provider, and a whole book at once would
multiply the spend per minute and collide with rate limits. The queue is visible
and any run can be stopped.

Expect a single run to take minutes, not seconds. Reports appear as each agent
files them. Reloading the page mid-run replays it from the beginning rather than
dropping you into the middle.

## 6. Read the result

The Portfolio Manager's rating is one of **Buy / Overweight / Hold / Underweight
/ Sell**, or **REVIEW**.

REVIEW is not a Hold. It means no rating could be read from the decision text,
so the run is recorded for a human to judge rather than as a position. Read the
decision, or run it again.

Every run also writes the markdown report tree under `~/.tradingagents/logs` and
appends to the memory log at `~/.tradingagents/memory/trading_memory.md` — the
same files a CLI run writes.

The **History** tab reads that memory log. A decision sits `pending` until its
holding window has traded, after which it is scored on realised alpha against
the instrument's regional benchmark, and the lesson is fed into the next run on
that ticker. This is why the system gets more useful the longer you run it.

---

## Troubleshooting

| What you see | What it means |
|---|---|
| `The web UI needs its extra dependencies` | `pip install ".[webui]"` |
| `API key for provider 'x' is not set` | the key is missing from `.env`, or `.env` is not in the directory you launched from |
| A run fails instantly | almost always the key. The run's error line names the variable to set |
| A run sits at "running" for minutes | normal. The Sentiment Analyst fetches StockTwits and Reddit, which are slow and rate-limited. Deselect it to skip |
| Rating is `REVIEW` | the model's decision had no readable rating. Re-run, or read the decision yourself |
| `nothing could be read from this file` | not a positions export, or the header row names no symbol and quantity column |
| A holding is missing after import | check the skipped list under the drop zone — options contracts and quantity-less rows are named there |
| The Runs list is empty after a restart | it is held in memory. The durable record is the report tree and the memory log, which History reads |
| Port already in use | `tradingagents ui --port 8787` |

### Reproducibility

Two runs of the same ticker and date can differ. The models sample
non-deterministically, and news and social sources move under you. Pinning the
analysis date fixes the price window but not the live sources. Lower
`TRADINGAGENTS_TEMPERATURE` if your model honours it; the current reasoning-first
models largely do not.

### Costs

The pipeline makes many model calls per run — analysts, two debates, three
decision agents. Before pointing it at a thirty-position book, run one ticker
and look at the LLM-call and token counts in the run header. Multiply.

---

## Running without the UI

Everything above works headless. The UI adds a browser and a saved book; it does
not add capability.

```bash
tradingagents --ticker NVDA --date 2026-09-23 --analysts market,news --save --no-show
tradingagents backtest NVDA,AAPL --start 2026-06-01 --end 2026-08-01 --every 7
```

See the [README](README.md) for the Python API, backtesting, checkpoint resume
and the full configuration surface, and [`webui/README.md`](webui/README.md) for
how the UI is put together.
