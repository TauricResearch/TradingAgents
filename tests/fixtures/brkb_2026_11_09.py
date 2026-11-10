"""A frozen BRK-B run: filings, prices, indicators and a simulated book (§4).

Every figure here is a constant. The point of the fixture is that a test can run
the whole pipeline and compare against expected values that were written down
independently of the code under test — a fixture computed by the code it checks
proves nothing.

Provenance of the numbers
-------------------------
The values come from the SEC companyfacts payload and the market snapshot that
the data-lineage audit examined (`docs/audits/`), which is the same evidence
that established the defects this suite guards against:

- **Q3 2026 consolidated revenue** ``105,647,000,000`` — the
  ``RevenueFromContractWithCustomerExcludingAssessedTax`` *and* ``Revenues``
  concept agree on it. The narrower component the defective extractor picked was
  ``74,322,000,000``.
- **Q3 2025 revenue** ``94,972,000,000``, so the year-over-year change is
  ``(105,647 - 94,972) / 94,972 = +11.24%``.
- **Shareholders' equity** ``800,000,000,000`` at 2026-09-30, with 550,000 class
  A shares (1,500 class B each) and 1,400,000,000 class B shares: 2,225,000,000
  class-B-equivalent shares, so a class-B book value of ``359.55``.
- **Price** ``576.74`` at an intraday instant on 2026-11-09, which is what makes
  the bar non-final: 18:37 Rome is 12:37 in New York, mid-session.
- **ATR(14)** ``9.524`` and **SMA200** ``502.85`` from the same snapshot.

The reported multiple the model wrote was ``1.73x``, and ``0.00116x`` in one
place — the latter is 1.604/1500, the A/B ratio applied backwards. Neither
reproduces from these inputs; ``576.74 / 359.55 = 1.604`` does.

Nothing here is computed by the modules under test. If a constant needs to
change, it is because the real vendor payload changed, not to make a test pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tests.fixtures.brk_b_2026_11_08 import BRK_A_TO_B_RATIO, TICKER

# --- SEC filings (point-in-time: known at the analysis date) ----------------

ANALYSIS_DATE = "2026-11-09"

Q3_2026 = {"start": "2026-07-01", "end": "2026-09-30"}
Q3_2025 = {"start": "2025-07-01", "end": "2025-09-30"}

REVENUE_Q3_2026 = 105_647_000_000.0
REVENUE_Q3_2025 = 94_972_000_000.0
# The narrower concept that exists in the same filing, which the defective
# extractor preferred because it was listed first.
REVENUE_Q3_2026_NARROW = 74_322_000_000.0

EQUITY = 800_000_000_000.0
SHARES_CLASS_A = 550_000.0
SHARES_CLASS_B = 1_400_000_000.0
CLASS_A_TO_B_RATIO = float(BRK_A_TO_B_RATIO)
CLASS_B_EQUIVALENT_SHARES = SHARES_CLASS_B + SHARES_CLASS_A * CLASS_A_TO_B_RATIO

# --- Market snapshot --------------------------------------------------------

PRICE = 576.74
SMA200 = 502.85
SMA50 = 545.10
PERIOD_HIGH = 812.35
ATR = 9.524
PREVIOUS_CLOSE = 573.50

# The instant the snapshot was taken: midday in New York, so the daily candle
# is still forming and its Close is not a close.
SNAPSHOT_INSTANT = "2026-11-09T17:37:00Z"      # 12:37 America/New_York

# --- The simulated book -----------------------------------------------------

CASH = 50_000.0
ACCOUNT_EQUITY = 100_000.0
RISK_PER_TRADE_PCT = 0.01
MAX_SYMBOL_EXPOSURE = 0.05
RISK_BUDGET = ACCOUNT_EQUITY * RISK_PER_TRADE_PCT      # 1,000 USD

# --- Expected values, computed by hand, independently of the code -----------

EXPECTED = {
    # (105,647 - 94,972) / 94,972
    "revenue_growth_pct": 11.2402,
    # 800e9 / 2.225e9
    "book_value_per_share": 359.5506,
    # 576.74 / 359.5506
    "price_to_book": 1.6041,
    # The model's own figures, none of which reproduces.
    "reported_price_to_book": 1.73,
    # The report's "0,00116x". The exact quotient of the A/B ratio applied
    # backwards is 1.6041/1500 = 0.0010694, so even this figure was the model's
    # own arithmetic rather than a computation — which is the finding, not a
    # rounding detail. Recorded as the claim it was.
    "reported_price_to_book_ratio_error": 0.00116,
    "class_ratio_inversion": 1.6041 / CLASS_A_TO_B_RATIO,   # 0.0010694
    # floor(1000 / (576.74 - 555.0)) with a 5% cap: the cap binds.
    "entry": 576.0,
    "stop": 555.0,
    "per_share_risk": 21.0,
    "atr_multiple": 21.0 / ATR,                        # 2.205
    "risk_budget_qty": 47,                             # floor(1000 / 21)
    "exposure_capped_qty": 8,                          # floor(5000 / 576)
    "binding_constraint": "EXPOSURE_CAP",
}

# The trader's plan as the model writes it: labelled, so the extractor reads it
# and never guesses a bare number out of prose.
TRADER_PLAN = (
    f"Entry {EXPECTED['entry']:.2f}, stop {EXPECTED['stop']:.2f}, "
    f"ATR {ATR:.3f}. Position sized against the risk budget."
)


@dataclass(frozen=True)
class BrkbFixture:
    """The whole frozen run, in one immutable object."""

    ticker: str = TICKER
    analysis_date: str = ANALYSIS_DATE
    revenue_q3_2026: float = REVENUE_Q3_2026
    revenue_q3_2025: float = REVENUE_Q3_2025
    revenue_q3_2026_narrow: float = REVENUE_Q3_2026_NARROW
    equity: float = EQUITY
    shares_class_a: float = SHARES_CLASS_A
    shares_class_b: float = SHARES_CLASS_B
    class_a_to_b_ratio: float = CLASS_A_TO_B_RATIO
    price: float = PRICE
    previous_close: float = PREVIOUS_CLOSE
    sma50: float = SMA50
    sma200: float = SMA200
    period_high: float = PERIOD_HIGH
    atr: float = ATR
    snapshot_instant: str = SNAPSHOT_INSTANT
    cash: float = CASH
    account_equity: float = ACCOUNT_EQUITY
    risk_budget: float = RISK_BUDGET
    max_symbol_exposure: float = MAX_SYMBOL_EXPOSURE
    trader_plan: str = TRADER_PLAN
    expected: dict = field(default_factory=lambda: dict(EXPECTED))

    # -- derived shapes the pipeline consumes -------------------------------

    def filings(self) -> list[dict]:
        """The filings known at the analysis date, oldest first."""
        return [
            {
                "form": "10-Q",
                "period_end": Q3_2025["end"],
                "filed": "2025-11-01",
                "accession": "0001067983-25-000042",
            },
            {
                "form": "10-Q",
                "period_end": Q3_2026["end"],
                "filed": "2026-11-01",
                "accession": "0001067983-26-000088",
            },
        ]

    def market_snapshot(self) -> dict:
        return {
            "close": self.price,
            "previous_close": self.previous_close,
            "sma50": self.sma50,
            "sma200": self.sma200,
            "high_52w": self.period_high,
            "currency": "USD",
            # The gate reads ``price_as_of``: an observation stamp under any
            # other key is silently ignored, and the audit then reports no bar
            # verdict at all — which reads exactly like "no bar was used".
            "price_as_of": self.snapshot_instant,
        }

    def portfolio(self) -> dict:
        return {
            "cash": self.cash,
            "equity": self.account_equity,
            "currency": "USD",
            "positions": [],
        }

    def run_state(self, **overrides) -> dict:
        """A finished run's state, as the graph would leave it.

        Reports are empty by default: the certified metrics must come from the
        supplied figures, not from prose the model wrote. Overrides let a
        negative test introduce exactly one defect.
        """
        state = {
            "company_of_interest": self.ticker,
            "trade_date": self.analysis_date,
            "market_report": "",
            "sentiment_report": "",
            "news_report": "",
            "fundamentals_report": "",
            "investment_plan": "",
            "trader_investment_plan": self.trader_plan,
            "final_trade_decision": "Buy.",
            "final_rating": "Overweight",
            "verified_market_snapshot": self.market_snapshot(),
            "equity": self.equity,
            "shares_class_a": self.shares_class_a,
            "shares_class_b": self.shares_class_b,
            "class_a_to_b_ratio": self.class_a_to_b_ratio,
            "price_class": "B",
            "currency": "USD",
            "revenue_consolidated": self.revenue_q3_2026,
            "revenue_prior": self.revenue_q3_2025,
            "investment_debate_state": {
                "bull_history": "", "bear_history": "",
                "history": "", "current_response": "",
            },
            "risk_debate_state": {
                "aggressive_history": "", "conservative_history": "",
                "neutral_history": "", "history": "",
            },
        }
        state.update(overrides)
        return state


BRKB = BrkbFixture()
