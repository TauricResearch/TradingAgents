# API Reference — Execution Engine

## Base Types

### `TradeOrder`

```python
@dataclass
class TradeOrder:
    action: str          # "buy" or "sell"
    token_in: str        # Input token address
    token_out: str       # Output token address
    amount: float        # Amount of token_in to spend
    slippage_bps: int    # Slippage tolerance in basis points (50 = 0.5%)
    chain: str           # "solana", "ethereum", "base", etc.
    priority_fee: float | None = None  # Optional gas/priority fee override
```

### `TradeResult`

```python
@dataclass
class TradeResult:
    success: bool
    tx_hash: str
    amount_in: float
    amount_out: float
    price_impact: float   # Percentage
    gas_cost: float       # In native token
    timestamp: str
```

---

## `JupiterExecutor` (Solana)

```python
from tradingagents.execution import JupiterExecutor

executor = JupiterExecutor(
    rpc_url="https://api.mainnet-beta.solana.com",
    private_key="<base58_private_key>",  # From SOLANA_PRIVATE_KEY
)
```

### Methods

#### `async get_quote(order: TradeOrder) -> dict`

Fetches a swap route from the Jupiter Aggregator V6 API.

```python
quote = await executor.get_quote(order)
# Returns raw Jupiter quote dict with fields like:
# { "inputMint": ..., "outputMint": ..., "outAmount": ... }
```

**Quota:** 1 HTTP GET to `https://quote-api.jup.ag/v6/quote`

#### `async execute_swap(order: TradeOrder) -> TradeResult`

Full swap execution:
1. Gets quote
2. POSTs to `/v6/swap` to get serialized transaction
3. Signs with `solders.Keypair`
4. Sends via Solana RPC

#### `async get_wallet_balance(token_address: str) -> float`

Returns the token balance for the configured wallet. *(Stub — implement for Scenario 3)*

---

## `OneInchExecutor` (EVM)

```python
from tradingagents.execution import OneInchExecutor

executor = OneInchExecutor(
    rpc_url="https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY",
    private_key="0x<hex_private_key>",  # From ETH_PRIVATE_KEY
    chain_id=1,  # 1=Ethereum, 8453=Base, 42161=Arbitrum
)
```

### Methods

#### `async get_quote(order: TradeOrder) -> dict`

Fetches price estimate from 1inch V6 API.

```python
quote = await executor.get_quote(order)
# Returns: { "dstAmount": "50000000000000000", ... }
```

#### `async execute_swap(order: TradeOrder) -> TradeResult`

Full EVM swap:
1. Calls `/swap/v6.0/{chainId}/swap` to get calldata
2. Builds EIP-155 transaction with nonce + gas
3. Signs with `web3.eth.account`
4. Broadcasts via `eth_sendRawTransaction`

---

## `OrderManager`

Converts LLM agent signals (`"BUY"`, `"SELL"`, `"HOLD"`) into executable `TradeOrder` objects.

```python
from tradingagents.execution import OrderManager

manager = OrderManager(
    risk_params={
        "max_position_size": 1000.0,  # USD
        "default_buy_amount": 100.0,  # USD per buy
    }
)
```

### `async process_signal(signal, token_address, portfolio, chain) -> TradeOrder | None`

| Signal | Behaviour |
|---|---|
| `"BUY"` | Spends `default_buy_amount` USDC → target token (capped by `max_position_size`) |
| `"SELL"` | Sells entire position of target token → USDC |
| `"HOLD"` | Returns `None` — no trade |

---

## `GoogleSearchClient` + `QuotaManager`

```python
import os
from tradingagents.dataflows.google_search_tools import GoogleSearchClient, QuotaExceededError

client = GoogleSearchClient(
    api_key=os.environ["GOOGLE_SEARCH_API_KEY"],
    cx=os.environ["GOOGLE_SEARCH_ENGINE_ID"],
    daily_limit=95,       # Hard cap — raises QuotaExceededError when reached
    warn_threshold=0.8,   # Logs warning at 80% usage
)

results = await client.search("solana DeFi TVL", num=5)
# Returns: list[SearchResult(title, link, snippet)]

print(client.quota_status)
# { "usage_today": 3, "daily_limit": 95, "remaining": 92, "is_near_limit": False }
```

---

## `WebResearchAnalyst`

```python
from tradingagents.agents.analysts.web_research_analyst import WebResearchAnalyst

analyst = WebResearchAnalyst()  # Reads GOOGLE_SEARCH_* from env

report = await analyst.research_token(
    token_name="Solana",
    token_address="So11111111111111111111111111111111111111112",
)

print(report.to_text())  # LLM-ready markdown report
```

### Report Categories

| Attribute | Description |
|---|---|
| `security_findings` | Results from honeypot.is, tokensniffer |
| `news_findings` | Results from coindesk, theblock, bloomberg |
| `analytics_findings` | Results from defillama, dune, dexscreener |
| `sentiment_findings` | Results from lunarcrush |
| `quota_status` | Current daily usage stats |

**Quota cost:** 4 queries per `research_token()` call (one per category).

---

## `PortfolioTracker`

```python
from tradingagents.portfolio import PortfolioTracker

tracker = PortfolioTracker(rpc_url="https://api.mainnet-beta.solana.com")
portfolio = await tracker.get_portfolio_state(wallet="<address>", chain="solana")

print(portfolio.total_value_usd)         # e.g. 5420.75
print(portfolio.positions["So1111..."])  # PositionInfo object
```

Stubs `_fetch_token_balances` and `_fetch_token_prices` — implement for Scenario 3 with real RPC/price oracle calls.
