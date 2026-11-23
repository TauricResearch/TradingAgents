# Research platform

A local platform on top of TradingAgents for studying how the agents decide over time:
run a watchlist, keep every decision, score the decisions against what prices did next,
and follow them with a simulated (paper) portfolio. Everything runs on your machine.

**Research and study only.** Nothing here connects to a broker or places an order. The
decisions come from LLM agents and can be wrong. Every number the platform reports
(returns, alpha, hit rates, position sizes, equity, drawdown) is computed in Python
from recorded decisions and historical closes; the model never produces a figure.

## Setup

1. Install the dashboard dependency into the repo's environment:

   ```bash
   pip install -e ".[platform]"
   ```

2. Put your Anthropic key in a `.env` file in the repo folder (it is gitignored):

   ```
   ANTHROPIC_API_KEY=...
   ```

   With no `TRADINGAGENTS_LLM_PROVIDER` set, the platform uses Anthropic with
   `claude-sonnet-5-5` for the analysts, researchers, debaters and trader, and
   `claude-opus-5-5` for the research and portfolio managers. To change them:

   ```
   TRADINGAGENTS_LLM_PROVIDER=anthropic
   TRADINGAGENTS_QUICK_THINK_LLM=claude-haiku-4-5
   TRADINGAGENTS_DEEP_THINK_LLM=claude-sonnet-5-5
   ```

   Any other provider the repo supports works the same way with its own key.

3. Optional, for better inputs: `FRED_API_KEY` (risk-free rate) and
   `SEC_EDGAR_USER_AGENT` (US filings) — see `.env.example`.

## Using it

### Dashboard

```bash
tradingagents-platform dashboard
```

Opens <http://127.0.0.1:8501> (local only). Pages:

| Page | What it does |
|---|---|
| Overview | Provider, models and whether the key is set; counts and the latest signals |
| Run analyses | Paste tickers, pick a date and analysts, run them all |
| Signals and reports | Every recorded run, its full report and final decision, and a price chart with each rating marked |
| Scorecard | How each rating did over 5, 21 and 63 trading days against the regional benchmark |
| Paper portfolio | A simulated book that follows the signals, with equity curve, trades and statistics |

### Command line

```bash
tradingagents-platform run AAPL MSFT 2222.SR            # today, default analysts
tradingagents-platform run --file watchlist.txt --date 2026-11-20
tradingagents-platform signals --csv signals.csv
tradingagents-platform scorecard --csv outcomes.csv
tradingagents-platform paper --cash 100000 --benchmark SPY
```

A watchlist file is plain text (one ticker per line or comma separated, `#` for
comments) or a JSON list. Tickers are checked and normalised like the main CLI
(`2222.sr` becomes `2222.SR`).

Each ticker is one full multi-agent run: several minutes and real API usage. A ticker
already recorded for the date is skipped (pass `--rerun` to run it again), so an
interrupted sweep continues by running it again. A failed ticker is recorded with its
reason and the sweep goes on.

Runs dated in the past are point-in-time like the rest of TradingAgents, which is how
you build a history to score without waiting: run a watchlist on a series of past dates.

## Where things are stored

`<results_dir>/platform/platform.db`, a SQLite file (default `results_dir` is
`~/.tradingagents/logs`). One row per ticker and date: the rating, the decision text, the
report folder, the models used, and the risk-based size, ATR stop, ATR and volatility
computed for that date by the same code as the risk-metrics step. The graph's own memory
log and report folders are written as usual.

## How the scorecard works

For a signal on analysis date D:

- **Entry** is the first final close strictly after D. The decision used closes up to D,
  so this is the earliest price anyone acting on it could have had.
- **Return** over h trading days = close[entry + h] / close[entry] − 1.
- **Benchmark return** uses the instrument's regional benchmark (the same one the memory
  log settles against), read on or before the entry and exit dates.
- **Alpha** = return − benchmark return.
- **Hit**: a Buy or Overweight is right when alpha > 0, an Underweight or Sell when
  alpha < 0. A Hold claims no direction, so it has no hit rate.
- **Spread**: the mean alpha of bullish signals minus that of bearish ones. A positive
  spread means the ratings sorted stocks the right way on average.

A horizon that has not finished trading is **pending**, never estimated.

Worked example (from the tests): closes 100 (D), 110, 121, 133.1 and benchmark 50, 50,
55, 55. Entry is 110 on D+1. Over 2 trading days the exit is 133.1, so the return is
133.1 / 110 − 1 = 21%. The benchmark goes 50 → 55 = 10%, so alpha = 11%, and for a Buy
that is a hit.

Read small samples with care: a hit rate over a handful of signals is mostly noise, and
one model sampling per cell means a re-run can rate differently.

## How the paper portfolio works

Fixed rules, so the same signals and prices always give the same result:

| Rating | Target weight of the book |
|---|---|
| Buy | the recorded risk-based size (ATR-stop sizing at 1% risk per position, capped), or 5% if none was recorded |
| Overweight | half that size (`overweight_scale`) |
| Hold | no trade |
| Underweight | half the current weight (`underweight_scale`) |
| Sell | zero |

- Long only, no leverage: a buy never spends more than the free cash (it is scaled down
  and the trade says so).
- A signal dated D trades at the ticker's first close after D.
- Commission and slippage are charged in basis points of traded value (5 + 5 by default).
- With stops on, a position opened or added to carries that signal's ATR stop. The first
  close below it sells the whole position at that close. This is a close-only check: an
  intraday break that recovers does not trigger, and a gap down fills at the close.
- Positions are valued in their own quote units and **currencies are not converted**. A
  portfolio mixing markets (US and `.SR`, say) is flagged; keep one market per portfolio
  for figures that mean something.

Worked example (from the tests): $100,000, a Buy with a recorded size of 20% on D. The
next close is 110, so $20,000 buys 181.8 units. When the price reaches 121 the position is
worth $22,000, the book $102,000: a 2% total return.

Statistics: total and annualised return, annualised volatility and Sharpe from daily
equity changes, maximum drawdown, average invested share, costs paid, and a buy-and-hold
benchmark over the same dates.

## Limits

- Text feeds (news, social) are not archived, so a past-dated run sees today's view of
  what was published then, as far as the vendors allow. Prices and SEC filings are
  point-in-time.
- One model sampling per run; set `TRADINGAGENTS_TEMPERATURE=0` for less variation.
- The paper portfolio is an illustration of the signals with simple rules, not an
  execution model: no partial fills, no borrow, no dividends, no FX.
- The platform runs one ticker at a time. A long watchlist takes a while.
