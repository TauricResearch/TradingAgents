"""Assistant settings, loaded from the repo-root .env via pydantic-settings.

Field names map case-insensitively to environment variables, so
``telegram_bot_token`` reads ``TELEGRAM_BOT_TOKEN``. LLM provider keys
(ANTHROPIC_API_KEY etc.) are read by the tradingagents package itself and are
intentionally not duplicated here.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ASSISTANT_HOME = Path.home() / ".tradingagents"


class AssistantSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Database ---
    # Default: SQLite under ~/.tradingagents, next to the engine's own state.
    assistant_db_url: str = ""

    # --- LLM used for scheduled runs ---
    # Any provider the engine supports works here: "anthropic" (default),
    # "ollama" for free local models (e.g. deep=qwen3:32b, quick=llama3.2),
    # "openai", "openai_compatible", etc. For Ollama the default endpoint is
    # http://localhost:11434/v1; point elsewhere via ASSISTANT_LLM_BACKEND_URL
    # or the engine's own OLLAMA_BASE_URL.
    assistant_llm_provider: str = "anthropic"
    assistant_deep_model: str = "claude-sonnet-4-6"
    assistant_quick_model: str = "claude-haiku-4-5"
    assistant_llm_backend_url: str = ""  # empty = provider's default endpoint

    # --- Anomaly screener ---
    # Daily quantitative discovery pass (no LLM cost). Auto-adds up to
    # ``screener_max_adds`` high-scoring under-followed candidates per run,
    # never growing the watchlist past ``screener_watchlist_cap``.
    screener_enabled: bool = True
    # Throttled to match deep-analysis capacity: adds queue for initiation
    # runs, so the faucet must not outrun the drain (~1/day ≈ initiation
    # budget under the weekly cap).
    # Raised from 1: the old value was tuned so the watchlist could not outrun
    # the LLM's ability to analyse it ("the faucet must not outrun the drain").
    # The drain was the Ollama budget. At 1 add/day against a 21-day expiry the
    # list barely moved, so a ticker that started performing could wait weeks
    # for a seat.
    screener_max_adds: int = Field(default=3, ge=0, le=10)
    # Satellite seats only — core (hand-picked giants/ETFs) live outside this
    # cap and never expire.
    # Wider is better for statistics: effective sample size comes from DISTINCT
    # names, not from analysing the same ones more often — repeat looks at one
    # ticker are correlated observations, which is exactly what made the July
    # screener finding evaporate.
    screener_satellite_cap: int = Field(default=20, ge=1)
    # Screener picks that stayed boring (weekly tier, no position, Hold) for
    # this many days fall off the list; the screener can re-discover them.
    screener_expiry_days: int = Field(default=21, ge=1)

    # --- Paper portfolio ---
    # Virtual starting cash (USD) per book. Changing it later does not reset
    # existing accounts.
    paper_starting_cash: float = Field(default=10_000.0, gt=0)

    # --- Liveness ---
    # External dead-man's switch. A dead process cannot report that it died, so
    # the scheduler pings this URL each pass and the monitor alerts when the
    # pings STOP. Unset = disabled. Free options: healthchecks.io, cronitor.
    assistant_heartbeat_url: str = ""

    # --- Index core (capital deployment) ---
    # Against an SPY benchmark, idle cash is an unfunded short: every dollar
    # not invested loses the equity risk premium. Both books measurably
    # suffered from this — strategic ran ~90% cash and tactical ~48% over
    # Jul-Aug 2026, and both trailed SPY despite decent picks. Sweeping idle
    # cash into the benchmark needs NO forecasting edge to be correct; a
    # replay of the recorded signals put it at +2.24pp over five weeks.
    # Satellite signals sell core to fund themselves and return proceeds on
    # exit, so the default state of any uncommitted dollar is "market return"
    # rather than zero.
    core_enabled: bool = True
    core_etf: str = "SPY"
    # Crash insurance on the core: hold the benchmark only while it trades
    # above its long-term average, else sit in cash. Measured on SPY
    # 1993-2026, this is the ONLY timing rule tested that beat an
    # exposure-matched no-skill blend — same return, HALF the drawdown
    # (-22% vs -46%), and it turned the 2008 crash from -46% into -12%.
    #
    # It is insurance, not alpha, and the premium is real: outside the GFC it
    # costs 3-5pp of CAGR (about $30-44/month on $10k) because it sits out
    # rallies. In 2008-2009 alone it was worth +18.9pp. Off by default so the
    # cost is always a deliberate choice.
    core_trend_filter: bool = False
    core_trend_window: int = Field(default=200, ge=20, le=400)
    # Cash kept uninvested so satellite entries never fail for want of
    # settlement headroom. 5% of a $10k book is $500 — roughly one position.
    core_cash_buffer_pct: float = Field(default=5.0, ge=0.0, le=50.0)
    # Skip core trades below this notional; churning $20 lots just pays costs.
    core_min_trade_usd: float = Field(default=100.0, gt=0)

    # --- Tactical layer (rule-based, no LLM) ---
    # DISABLED by default: the shipped 10-year backtest showed every rule in
    # the library losing to buy-and-hold risk-adjusted on the core universe
    # (see scripts/backtest_tactical.py). A wider 2026 re-test on 63 tickers
    # over 20 years was harsher still — against an EXPOSURE-MATCHED static
    # cash blend (same average exposure, zero timing skill) trend_following
    # was 1.6pp worse on drawdown and 2.19pp worse on CAGR, so even its
    # crash-protection claim did not survive the right control.
    tactical_rule: str = ""
    # Which names the rule may trade. "us_core" is the original 7-name US
    # large-cap set the rule was backtested on; "all" gives it the SAME pool the
    # LLM sees, so both engines face identical candidates and any divergence is
    # attributable to the engine rather than to the universe.
    #
    # Widening does NOT create alpha — measured on the screener picks the rule
    # returned Sharpe 0.25 against 0.33 for a zero-skill exposure-matched blend,
    # losing just as it does on large caps. It makes the comparison fair, which
    # is a different and still worthwhile thing.
    tactical_universe: str = "all"          # us_core | us_all | all
    tactical_size_pct: float = Field(default=0.10, gt=0, le=0.25)
    tactical_max_positions: int = Field(default=8, ge=1, le=20)
    tactical_daily_loss_cap_pct: float = Field(default=3.0, gt=0)
    # Trailing stop for rule-driven positions. A FIXED volatility stop fights
    # a trend rule: it fires on noise long before the trend breaks, so every
    # exit lands at a loss. Both 2026 stop-outs (AMZN, LLY) were re-entered
    # higher days later, and the tactical book closed 2 trades for 2 losses.
    # A ratcheting stop keeps the downside guard while letting winners run,
    # which is what makes a profitable exit possible at all.
    tactical_trailing_stop_enabled: bool = True
    tactical_trail_pct: float = Field(default=12.0, gt=0, le=50.0)
    # Bar a symbol from re-entry for this many days after an exit, so the
    # rule cannot immediately buy back what the stop just sold.
    tactical_reentry_cooldown_days: int = Field(default=5, ge=0)

    # --- Watchlist rotation ---
    # After this many consecutive Hold ratings a ticker drops from daily to
    # weekly runs; any non-Hold rating promotes it straight back to daily.
    assistant_demote_after_holds: int = Field(default=5, ge=1)
    # Event thresholds and default stops are volatility-scaled per ticker —
    # see app/services/volatility.py for the multipliers and bounds.

    # --- Run schedule ---
    # Analysis windows are DB-backed "schedule slots" managed from the web
    # dashboard (up to N per day, each with its own time/market/budget).
    # This global cap is the safety net: no matter how slots are configured,
    # at most this many ticker-runs happen per UTC day — protects a limited
    # LLM quota (e.g. Ollama cloud free tier) from a misconfigured schedule.
    # Sized for DATA VOLUME, not for quota preservation. The Ollama weekly cap
    # that these were built around is gone; the binding constraint now is the
    # opposite — August's verdict was unprovable at an effective sample size of
    # 3.19, so an unused slot costs an observation we cannot get back. These
    # remain as a guard against a misconfigured schedule or a retry loop, not
    # as a throttle on ambition.
    assistant_daily_run_budget: int = Field(default=30, ge=1)
    # Weekly governor on top of the daily one: with Ollama cloud free tier a
    # deep run costs ~8-9% of the weekly allowance, so ~11 runs/week is the
    # sustainable ceiling. A violent Monday can't starve Friday.
    assistant_weekly_run_budget: int = Field(default=200, ge=1)

    # --- Telegram ---
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # --- Email (digest per market run) ---
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    email_from: str = ""
    email_to: str = ""

    @property
    def database_url(self) -> str:
        if self.assistant_db_url:
            return self.assistant_db_url
        db_path = _ASSISTANT_HOME / "assistant.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite+aiosqlite:///{db_path.as_posix()}"

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_username and self.smtp_password and self.email_to)


@lru_cache
def get_settings() -> AssistantSettings:
    return AssistantSettings()
