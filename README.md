# Koral Equities

**Independent AI equity research • Systematic stock screening • Paper portfolio management**

Koral Equities is a UK-focused research project exploring AI-assisted, long-only U.S. equity strategies. It runs a team of specialist language-model researchers, records competing investment arguments, and routes stock recommendations to a **separate, deterministic simulation engine**.

> **Paper trading only.** No brokerage order connection, no access to the owner's Trading 212 Stocks & Shares ISA, and no demonstrated trading edge. Historical and forward performance must be independently verified before allocating capital.

## Get started — Windows

Requires Python 3.11 or later. In the project folder:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\koral-equities-paper.exe init  # Only once! Existing users must skip.
.\.venv\Scripts\koral-equities.exe
```

Open **http://127.0.0.1:8765** to view the premium local trading desk.

The simulator keeps its data in `~/.tradingagents/paper/portfolio.json`. **Never run `init` to refresh or clear an existing account.** No real trades can be placed.

## Research and trading tools

| Module | Purpose |
| --- | --- |
| Premium research desk | Koral Equities dashboard, account metrics, AI ratings, journals and scan logs |
| Analyst team | Market, news, sentiment and fundamentals research |
| Investment committee | Bull/bear debate, risk discussion and portfolio review |
| Paper engine | £10,000 starting cash; 2% intended stop-risk budget; 6% aggregate planned risk; next-session simulation |
| Research screener | Offline momentum and liquidity screening prototype with point-in-time validation rules |
| Experiments | Independent comparison against simple quantitative portfolios and an investable benchmark (in development) |

The `Overweight` and `Underweight` labels express **relative allocation intent**; they are not unconditional market orders. **Known research-execution mismatch:** the initial paper CLI currently translates any `Overweight` into a next-session Buy, even when the report requires a specific price trigger, staging or other conditions. It is a baseline experiment only. Do not connect real capital or treat the queued orders as faithful implementations of the AI plans until a structured execution contract is built and validated.

## AI provider

The framework supports several model providers. To use the eligible ChatGPT subscription integration, set `TRADINGAGENTS_LLM_PROVIDER=chatgpt` in your private `.env`, then sign in:

```powershell
.\.venv\Scripts\koral-equities-research.exe login chatgpt
```

Availability depends on the account's supported plan and permissions. Never commit credentials to GitHub.

## Documents

- [Paper trading setup and risk assumptions](README_PAPER.md)
- [Dashboard and controls](README_DASHBOARD.md)
- [Research mandate](RESEARCH_CHARTER.md)
- [Project change history](CHANGELOG.md)
- [Open-source credits and provenance](UPSTREAM_ATTRIBUTION.md)
- [Original framework change history](UPSTREAM_CHANGELOG.md)
- [Apache 2.0 licence](LICENSE)

## Licence and provenance

Koral Equities includes modified, Apache-2.0-licensed software based on the open-source **TradingAgents** framework from **Tauric Research**, © original respective contributors. The paper engine, dashboard, brand and research-specific additions are modifications to that framework. See [UPSTREAM_ATTRIBUTION.md](UPSTREAM_ATTRIBUTION.md) and [LICENSE](LICENSE) for the original project attribution and licence requirements. This project is not affiliated with or endorsed by the original authors.
