"""What the trader trades, its strategy constants, and the settings read from .env.

The strategy constants are frozen for the validation period: changing one
changes the strategy under test, so they live in code rather than in the
environment. The models and their prices may also come from the dashboard's
``TRADER_HOME/settings.json`` (ADR 0007), which wins over .env.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from trader import overrides, prices
from trader.okx_private import OKXCredentials
from tradingagents.default_config import DEFAULT_CONFIG


@dataclass(frozen=True)
class Coin:
    """A watchlist entry: the instrument researched and the markets traded for it."""

    research: str  # Yahoo ticker the graph researches, e.g. BTC-USD
    swap: str      # OKX USDT-margined perpetual the trader holds, e.g. BTC-USDT-SWAP
    spot: str      # OKX spot pair the baseline holds, e.g. BTC-USDT


WATCHLIST: tuple[Coin, ...] = (
    Coin("BTC-USD", "BTC-USDT-SWAP", "BTC-USDT"),
    Coin("ETH-USD", "ETH-USDT-SWAP", "ETH-USDT"),
    Coin("SOL-USD", "SOL-USDT-SWAP", "SOL-USDT"),
)

# A full position unit loses RISK_PER_UNIT of equity when its stop, set
# STOP_ATR_MULT daily ATRs from entry, is hit.
RISK_PER_UNIT = 0.02
STOP_ATR_MULT = 2.5
ATR_DAYS = 14

# Target position per rating, in full position units. A rating missing here
# (Hold, REVIEW, or no rating because the run failed) keeps the current position.
# Shorts are half size because the rating prompts were written long-only (ADR 0003).
RATING_WEIGHTS = {"Buy": 1.0, "Overweight": 0.5, "Underweight": -0.25, "Sell": -0.5}

MAX_COIN_EXPOSURE = 1.0    # notional per contract, as a multiple of equity
MAX_GROSS_EXPOSURE = 2.0   # notional across contracts, as a multiple of equity
REBALANCE_THRESHOLD = 0.1  # trades smaller than this many full units are skipped

TAKER_FEE = 0.0005
SLIPPAGE = 0.0005
KILL_DRAWDOWN = 0.20  # drawdown from peak equity that flattens everything and halts trading

MAX_ATTEMPTS = 3                # research tries per coin per trade date
RETRY_WAIT_SECONDS = 30 * 60
BUDGET_LEARNING_DAYS = 7        # full UTC days of costs observed before the monthly cap is set
BUDGET_HEADROOM = 1.5           # monthly cap = mean daily cost * 30 * BUDGET_HEADROOM

ANALYSTS = ("market", "social", "news")
BENCHMARK = "USDC-USD"  # settles a rating's alpha against holding cash
GLOBAL_NEWS_QUERIES = (
    # Single words: Yahoo's fuzzy search drifts on phrases ("solana crypto"
    # returns First Solar). Crypto first, as the search stops at the article limit.
    "Bitcoin",
    "Ethereum",
    "Solana",
    "cryptocurrency",
    "Federal Reserve interest rates inflation",
)


def _price(name: str) -> tuple[float, float] | None:
    """Read an ``"input,output"`` price in USD per million tokens; None when unset."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        input_price, output_price = (float(part) for part in raw.split(","))
    except ValueError:
        raise ValueError(
            f'{name} must be "input,output" in USD per million tokens, got {raw!r}'
        ) from None
    return input_price, output_price


def _model_price(
    model: str, data: dict | None, from_env: tuple[float, float] | None
) -> tuple[float, float] | None:
    """The price of ``model``: settings.json's (``data``, as loaded), else the official
    table's, else ``from_env`` (the TRADER_PRICE_* value), else None."""
    saved = (data or {}).get("prices", {}).get(model)
    if saved is not None:
        return float(saved[0]), float(saved[1])
    official = prices.lookup(model)
    if official is not None:
        return official.input, official.output
    return from_env


@dataclass(frozen=True)
class Settings:
    """Settings that differ per machine, read from the environment (.env) and from
    the dashboard's settings.json (ADR 0007)."""

    home: Path
    capital: float | None = None
    price_deep: tuple[float, float] | None = None
    price_quick: tuple[float, float] | None = None
    telegram_token: str | None = None
    telegram_chat_id: str | None = None
    llm: dict | None = None  # the "llm" object of settings.json; None without the file
    web_token: str | None = None  # the dashboard's write endpoint wants it as a Bearer token
    okx_demo: OKXCredentials | None = None  # the demo account's API key (ADR 0008); masked repr

    @property
    def ledger_path(self) -> Path:
        return self.home / "ledger.sqlite"

    @property
    def lock_path(self) -> Path:
        return self.home / "trader.lock"

    @property
    def memory_log_path(self) -> Path:
        return self.home / "memory" / "trading_memory.md"

    # The intraday account (ADR 0006) keeps its own ledger and lock under ``home``.
    @property
    def intraday_ledger_path(self) -> Path:
        return self.home / "intraday" / "ledger.sqlite"

    @property
    def intraday_lock_path(self) -> Path:
        return self.home / "intraday" / "trader.lock"

    # The demo account (ADR 0008) likewise.
    @property
    def demo_ledger_path(self) -> Path:
        return self.home / "demo" / "ledger.sqlite"

    @property
    def demo_lock_path(self) -> Path:
        return self.home / "demo" / "trader.lock"

    @classmethod
    def from_env(cls) -> Settings:
        """The environment's settings with TRADER_HOME/settings.json applied."""
        home = os.getenv("TRADER_HOME", "").strip()
        return cls.with_overrides(
            Path(home).expanduser() if home else Path.home() / ".tradingagents" / "trader"
        )

    @classmethod
    def with_overrides(cls, home: Path) -> Settings:
        """The environment's settings with ``home``/settings.json applied (ADR 0007).

        ``llm`` is the file's; each tier's price is the file's for the tier's model,
        else the official table's (trader.prices), else TRADER_PRICE_DEEP/QUICK's, else
        None. The tier's model is the file's, else DEFAULT_CONFIG's, which carries the
        .env one. Without the file and an official price, the settings are the
        environment's alone.
        """
        capital = os.getenv("TRADER_CAPITAL", "").strip()
        # Read first, so a malformed value fails the run whatever price source wins.
        env_deep, env_quick = _price("TRADER_PRICE_DEEP"), _price("TRADER_PRICE_QUICK")
        data = overrides.load(home)
        models = overrides.tier_models(data)
        deep = models.get("deep_think_llm") or DEFAULT_CONFIG["deep_think_llm"]
        quick = models.get("quick_think_llm") or DEFAULT_CONFIG["quick_think_llm"]
        return cls(
            home=home,
            capital=float(capital) if capital else None,
            price_deep=_model_price(deep, data, env_deep),
            price_quick=_model_price(quick, data, env_quick),
            telegram_token=os.getenv("TRADER_TELEGRAM_TOKEN") or None,
            telegram_chat_id=os.getenv("TRADER_TELEGRAM_CHAT_ID") or None,
            llm=data["llm"] if data else None,
            web_token=os.getenv("TRADER_WEB_TOKEN", "").strip() or None,
            okx_demo=OKXCredentials.from_env(),
        )
