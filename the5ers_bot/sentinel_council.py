"""
sentinel_council.py
===================
The **Sentinel Council** - the risk brain of the AI Co-Pilot for a The5ers
*Bootcamp* evaluation account. It has two layers:

1. **Risk Auditor (deterministic, always on)** - :class:`RiskEngine` hard-codes the
   prop-firm guardrails and returns a :class:`RiskAssessment`. It needs no API key
   and is the *authoritative* gate: lot sizing, the RRR floor, the daily trade cap,
   the circuit breaker / kill-switch and the liquidity-session filter all live here.
2. **LLM Council (advisory, optional)** - a Groq *Scout* (trend/momentum) and a
   Gemini *Risk Auditor* read the same setup and add a plain-English opinion. It is
   advisory only, hard-timeboxed and fails **open** so it can never block the trader.

Risk model - The5ers Bootcamp ($5,000 demo, scaling to $20,000)
---------------------------------------------------------------
* Account base        : **$5,000 demo** (the same engine scales cleanly to a
                         **$20,000** funded/evaluation account - the risk rules are
                         fixed dollar amounts, so only the R-multiple percentages move)
* Fixed risk per trade  : **1R = $10**
* Reward:risk floor     : **RRR >= 1 : 1.5** (i.e. TP >= $15)
* Max trades per day    : **3**
* Circuit breaker       : lockout once the day's **net** P&L reaches **-$20 (2R)**
                          and a hard kill at **-$30 (3R)**; also locks once the
                          **+$50** daily profit target is banked.
* Session filter        : only London open (07:00-16:00 UTC) and the London/New
                          York overlap (12:00-16:00 UTC) are tradable.

Every guardrail is measured against the day's **net P&L change** (realized + floating
trading P&L), never against the account balance - funding/deposit deals are filtered
out at the data layer so a fresh $5,000 demo can never look like a profit-target hit.

Resilience
----------
Both LLM counselors walk a prioritised model cascade and fall through to the next
model on any API error, rate-limit or timeout:

* Scout (Groq)         : ``openai/gpt-oss-120b`` -> ``qwen/qwen3.8-27b`` -> ``openai/gpt-oss-20b``
* Risk Auditor (Gemini): ``gemini-2.5-flash`` -> ``gemini-2.5-flash-lite`` -> ``gemini-3.8-flash``

The Scout cascade runs under one hard deadline (``DEFAULT_TIMEOUT`` = 8s); the Gemini
Risk Auditor gets its own, more generous budget (``AUDITOR_TIMEOUT`` = 10s) so a
spiky ``generate_content`` call is not cut off prematurely. If a provider dies
outright the survivor carries the verdict; if both fail (or keys are absent) the
council fails open and the deterministic :class:`RiskEngine` alone decides.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

LOGGER = logging.getLogger("copilot.council")

DEFAULT_TIMEOUT = 8.0

# The Gemini Risk Auditor gets its own, more generous request budget: Gemini's
# generate_content latency is spikier than Groq's, and the old shared
# DEFAULT_TIMEOUT/len(cascade) split gave each auditor model only ~2.5s, which
# timed out prematurely. 10s lets a single Gemini call finish comfortably.
AUDITOR_TIMEOUT = 10.0

# --------------------------------------------------------------------------- #
# Risk rules - The5ers Bootcamp ($5,000 demo, scaling to $20,000)
# --------------------------------------------------------------------------- #
ACCOUNT_SIZE_USD = 5_000.0                    # demo base account
ACCOUNT_SIZE_MAX_USD = 20_000.0               # scale-up / funded target
RISK_PER_TRADE_USD = 10.0                     # 1R
MIN_RRR = 1.5                                 # 1 : 1.5
MIN_TP_USD = RISK_PER_TRADE_USD * MIN_RRR     # $15 minimum take-profit
MAX_TRADES_PER_DAY = 3
DAILY_LOSS_LOCK_USD = -20.0                   # 2R -> soft lockout
DAILY_LOSS_KILL_USD = -30.0                   # 3R -> hard kill-switch
DAILY_PROFIT_TARGET_USD = 50.0                # +5R: bank the day and stop (range +$50..+$100)
CIRCUIT_WATCH_USD = -10.0                     # 1R -> amber warning

VALID_DIRECTIONS = {"long", "short", "neutral"}

# --------------------------------------------------------------------------- #
# Liquidity sessions (UTC)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Session:
    """A tradable liquidity window, expressed in fractional UTC hours."""

    name: str
    start_hour: float
    end_hour: float
    anchor: str = ""  # the swing high/low the stop should sit behind

    def active(self, hour: float) -> bool:
        return self.start_hour <= hour < self.end_hour


LONDON_OPEN = Session("London open", 7.0, 16.0, anchor="session low/high")
LONDON_NY_OVERLAP = Session("London/New York overlap", 12.0, 16.0, anchor="session low/high")
PRIMARY_SESSIONS: tuple[Session, ...] = (LONDON_OPEN, LONDON_NY_OVERLAP)


def utc_hour(now: Optional[datetime] = None) -> float:
    """Fractional UTC hour (e.g. 12:30 -> 12.5)."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    return now.hour + now.minute / 60.0


def active_sessions(now: Optional[datetime] = None) -> List[str]:
    """Names of the primary sessions open at ``now`` (may be empty)."""
    hour = utc_hour(now)
    return [s.name for s in PRIMARY_SESSIONS if s.active(hour)]


def session_ok(now: Optional[datetime] = None) -> bool:
    """True when at least one primary liquidity session is open."""
    return bool(active_sessions(now))


# --------------------------------------------------------------------------- #
# Parsing / math helpers
# --------------------------------------------------------------------------- #
def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_direction(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in VALID_DIRECTIONS:
        return text
    if text.startswith("l") or text in {"buy", "bullish", "up"}:
        return "long"
    if text.startswith("s") or text in {"sell", "bearish", "down"}:
        return "short"
    return "neutral"


def size_lot(
    risk_usd: float,
    stop_distance: float,
    value_per_unit_per_lot: float,
    min_lot: float = 0.01,
    max_lot: float = 100.0,
    lot_step: float = 0.01,
) -> float:
    """Micro-lot sizing: ``lot = risk / (stop_distance * value_per_price_unit)``.

    The result is snapped to ``lot_step`` and clamped into ``[min_lot, max_lot]``.
    When the ideal size is below ``min_lot`` the position is fractionally too big;
    the caller flags that via :meth:`RiskEngine.assess`.
    """
    if stop_distance <= 0 or value_per_unit_per_lot <= 0:
        return float(min_lot)
    raw = risk_usd / (stop_distance * value_per_unit_per_lot)
    step = lot_step if lot_step and lot_step > 0 else 0.01
    snapped = round(raw / step) * step
    clamped = max(min_lot, min(max_lot, snapped))
    return round(clamped, 2)


# --------------------------------------------------------------------------- #
# Risk assessment
# --------------------------------------------------------------------------- #
@dataclass
class RiskAssessment:
    """Deterministic outcome of the :class:`RiskEngine` gate."""

    circuit: str = "SAFE"              # SAFE | WATCH | LOCKED
    locked: bool = False
    lock_reasons: List[str] = field(default_factory=list)

    session_ok: bool = True
    sessions: List[str] = field(default_factory=list)

    trades_today: int = 0
    trades_remaining: int = MAX_TRADES_PER_DAY
    trades_ok: bool = True

    daily_pnl: float = 0.0
    drawdown_ok: bool = True
    profit_target_hit: bool = False
    profit_target: float = DAILY_PROFIT_TARGET_USD

    direction: str = "neutral"
    symbol: str = ""
    entry: float = 0.0
    stop: float = 0.0
    take_profit: float = 0.0
    stop_distance: float = 0.0
    tp_distance: float = 0.0

    lot: float = 0.0
    rrr: float = 0.0
    rrr_ok: bool = False
    risk_usd: float = 0.0
    reward_usd: float = 0.0
    lot_capped: bool = False

    allowed: bool = False
    messages: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RiskEngine:
    """Hard-codes the prop-firm guardrails. Deterministic, no I/O, no API keys."""

    def __init__(
        self,
        account_size: float = ACCOUNT_SIZE_USD,
        risk_per_trade: float = RISK_PER_TRADE_USD,
        min_rrr: float = MIN_RRR,
        max_trades: int = MAX_TRADES_PER_DAY,
        loss_lock: float = DAILY_LOSS_LOCK_USD,
        loss_kill: float = DAILY_LOSS_KILL_USD,
        profit_target: float = DAILY_PROFIT_TARGET_USD,
        watch_level: float = CIRCUIT_WATCH_USD,
        enforce_session: bool = True,
        lot_floor: float = 0.01,
        lot_ceiling: float = 100.0,
    ) -> None:
        self.account_size = float(account_size)
        self.risk_per_trade = float(risk_per_trade)
        self.min_rrr = float(min_rrr)
        self.max_trades = int(max_trades)
        self.loss_lock = float(loss_lock)
        self.loss_kill = float(loss_kill)
        self.profit_target = float(profit_target)
        self.watch_level = float(watch_level)
        self.enforce_session = bool(enforce_session)
        self.lot_floor = float(lot_floor)
        self.lot_ceiling = float(lot_ceiling)

    # ------------------------------------------------------------------ #
    # Circuit breaker
    # ------------------------------------------------------------------ #
    def circuit(
        self,
        daily_pnl: float,
        trades_today: int = 0,
        profit_target: Optional[float] = None,
    ) -> tuple[str, bool, List[str]]:
        """Return ``(state, locked, reasons)`` for the kill-switch indicator."""
        target = self.profit_target if profit_target is None else float(profit_target)
        reasons: List[str] = []
        locked = False

        if daily_pnl <= self.loss_kill:
            locked = True
            reasons.append(f"Hard kill-switch: daily P&L {daily_pnl:+.2f} hit the {self.loss_kill:+.0f} (3R) limit.")
        elif daily_pnl <= self.loss_lock:
            locked = True
            reasons.append(f"Circuit breaker: daily P&L {daily_pnl:+.2f} hit the {self.loss_lock:+.0f} (2R) limit.")

        if daily_pnl >= target:
            locked = True
            reasons.append(f"Daily profit target {target:+.0f} reached ({daily_pnl:+.2f}) - bank it and stop.")

        if trades_today >= self.max_trades:
            locked = True
            reasons.append(f"Max trades/day reached ({trades_today}/{self.max_trades}).")

        if locked:
            return "LOCKED", True, reasons
        if daily_pnl <= self.watch_level:
            return "WATCH", False, [f"Caution: {daily_pnl:+.2f} down ({abs(daily_pnl)/max(self.risk_per_trade,1e-9):.1f}R)."]
        return "SAFE", False, []

    # ------------------------------------------------------------------ #
    # Full assessment
    # ------------------------------------------------------------------ #
    def assess(self, setup: Dict[str, Any]) -> RiskAssessment:
        """Grade a single setup against every rule. Never raises."""
        result = RiskAssessment()
        try:
            now = setup.get("now")
            if isinstance(now, str):
                now = None
            daily_pnl = _f(setup.get("daily_pnl"), 0.0)
            trades_today = int(_f(setup.get("trades_today"), 0.0))
            target = _f(setup.get("profit_target"), self.profit_target) if setup.get("profit_target") is not None else self.profit_target

            result.daily_pnl = daily_pnl
            result.trades_today = trades_today
            result.profit_target = target
            result.trades_remaining = max(0, self.max_trades - trades_today)
            result.trades_ok = trades_today < self.max_trades

            state, locked, reasons = self.circuit(daily_pnl, trades_today, target)
            result.circuit = state
            result.locked = locked
            result.lock_reasons = reasons
            result.drawdown_ok = daily_pnl > self.loss_lock
            result.profit_target_hit = daily_pnl >= target

            sessions = active_sessions(now)
            result.sessions = sessions
            result.session_ok = session_ok(now) if self.enforce_session else True

            direction = _normalize_direction(setup.get("direction"))
            result.direction = direction
            result.symbol = str(setup.get("symbol", ""))
            entry = _f(setup.get("entry"))
            stop = _f(setup.get("stop"))
            take_profit = _f(setup.get("take_profit"))
            result.entry, result.stop, result.take_profit = entry, stop, take_profit

            if direction == "long":
                stop_distance = entry - stop
                tp_distance = take_profit - entry
            elif direction == "short":
                stop_distance = stop - entry
                tp_distance = entry - take_profit
            else:
                stop_distance = tp_distance = 0.0

            result.stop_distance = max(0.0, stop_distance)
            result.tp_distance = max(0.0, tp_distance)

            value_per_unit = _f(setup.get("value_per_unit"), 100_000.0)
            min_lot = _f(setup.get("min_lot"), self.lot_floor) or self.lot_floor
            max_lot = _f(setup.get("max_lot"), self.lot_ceiling) or self.lot_ceiling
            lot_step = _f(setup.get("lot_step"), 0.01) or 0.01

            supplied_lot = setup.get("lot")
            if supplied_lot is not None:
                lot = round(max(min_lot, min(max_lot, _f(supplied_lot))), 2)
            else:
                lot = size_lot(self.risk_per_trade, result.stop_distance, value_per_unit, min_lot, max_lot, lot_step)
            result.lot = lot

            result.rrr = round(result.tp_distance / result.stop_distance, 2) if result.stop_distance > 0 else 0.0
            result.rrr_ok = result.rrr >= self.min_rrr

            result.risk_usd = round(result.stop_distance * value_per_unit * lot, 2)
            result.reward_usd = round(result.tp_distance * value_per_unit * lot, 2)
            result.lot_capped = (
                supplied_lot is None
                and result.stop_distance > 0
                and value_per_unit > 0
                and round(self.risk_per_trade / (result.stop_distance * value_per_unit), 4) < min_lot
            )

            if direction == "neutral":
                result.messages.append("No directional signal - nothing to size.")
            elif result.stop_distance <= 0:
                result.messages.append("Invalid stop: it must sit on the risk side of the entry.")
            elif result.tp_distance <= 0:
                result.messages.append("Invalid target: it must sit on the reward side of the entry.")

            if result.lot_capped:
                result.messages.append(
                    f"Stop is wide: the {min_lot:.2f} min lot risks {result.risk_usd:+.2f} (> 1R = ${self.risk_per_trade:.0f})."
                )
            if not result.rrr_ok and result.stop_distance > 0 and result.tp_distance > 0:
                result.messages.append(f"RRR {result.rrr:.2f} is below the {self.min_rrr:g}:1 floor.")
            if self.enforce_session and not result.session_ok:
                result.messages.append("Outside London / London-NY overlap - no new signals.")
            if result.profit_target_hit:
                result.messages.append(f"Daily profit target hit ({daily_pnl:+.2f}).")

            result.allowed = (
                not result.locked
                and result.session_ok
                and result.trades_ok
                and result.rrr_ok
                and direction != "neutral"
                and result.stop_distance > 0
                and result.tp_distance > 0
            )
            return result
        except Exception as exc:  # noqa: BLE001 - the gate must never crash the UI
            LOGGER.warning("risk assess failed: %s", exc)
            result.messages.append(f"Risk engine error: {exc}")
            result.allowed = False
            return result


# --------------------------------------------------------------------------- #
# Data objects (LLM council)
# --------------------------------------------------------------------------- #
@dataclass
class CounselorOpinion:
    role: str
    provider: str
    model: str
    verdict: str = "neutral"
    confidence: float = 0.0
    summary: str = ""
    compliant: Optional[bool] = None
    ok: bool = False
    error: str = ""
    raw: str = ""
    fallback: bool = False
    attempted: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CouncilVerdict:
    verdict: str = "neutral"
    confidence: float = 0.0
    approved: bool = True  # fail-open
    rrr_ok: bool = True
    summary: str = ""
    notes: str = ""
    consensus: bool = False
    degraded: bool = True
    scout_model_used: str = ""
    auditor_model_used: str = ""
    fallback_used: bool = False
    elapsed_ms: int = 0
    messages: List[str] = field(default_factory=list)
    scout: Optional[CounselorOpinion] = None
    auditor: Optional[CounselorOpinion] = None
    risk: Optional[RiskAssessment] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------- #
# LLM prompts
# --------------------------------------------------------------------------- #
SCOUT_MODELS: List[str] = [
    "openai/gpt-oss-120b",
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-20b",
]
AUDITOR_MODELS: List[str] = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3.8-flash",
]

_SCOUT_SYSTEM = (
    "You are Scout, a technical analyst on a manual day/swing trading desk. Judge the "
    "momentum and structure of the setup using the provided EMA50/EMA200 relationship, "
    "RSI(14) and ATR context. Answer LONG, SHORT or NEUTRAL and be decisive. "
    'Reply with ONLY JSON: {"verdict":"long"|"short"|"neutral","confidence":0.0-1.0,'
    '"summary":"one short sentence"}.'
)

_AUDITOR_SYSTEM = (
    "You are the Risk Auditor for a The5ers Bootcamp evaluation account: a $5,000 "
    "demo scaling to $20,000. "
    "Hard rules: risk per trade is 1R = $10, the take-profit must be at least 1.5x the "
    "stop (RRR >= 1:1.5, i.e. >= $15), at most 3 trades per day, the daily profit "
    "target is +$50, the circuit breaker locks out at -$20 (2R) and the hard kill-switch "
    "is -$30 (3R). Signals are only valid during the London open or the London/New York "
    "overlap. All limits apply to the day's NET P&L change (realized + floating), never "
    "to the account balance. "
    "Validate the setup against these rules using the reported numbers. Be conservative. "
    'Reply with ONLY JSON: {"verdict":"long"|"short"|"neutral","confidence":0.0-1.0,'
    '"compliant":true|false,"summary":"one short sentence of auditor notes"}.'
)


# --------------------------------------------------------------------------- #
# Sync bridge (own event-loop thread)
# --------------------------------------------------------------------------- #
class _Runner:
    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, name="council-async", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def run(self, coro: Any, timeout: float) -> Any:
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    def close(self) -> None:
        try:
            self._loop.call_soon_threadsafe(self._loop.stop)
        except Exception:  # pragma: no cover
            pass


# --------------------------------------------------------------------------- #
# Council
# --------------------------------------------------------------------------- #
class SentinelCouncil:
    """Risk Engine + optional LLM council. Advisory only, fail-open, never raises."""

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        groq_api_key: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        enabled: bool = True,
        scout_models: Optional[Sequence[str]] = None,
        auditor_models: Optional[Sequence[str]] = None,
        risk_engine: Optional[RiskEngine] = None,
        auditor_timeout: float = AUDITOR_TIMEOUT,
    ) -> None:
        self.timeout = float(timeout) if timeout and timeout > 0 else DEFAULT_TIMEOUT
        self.auditor_timeout = (
            float(auditor_timeout) if auditor_timeout and auditor_timeout > 0 else AUDITOR_TIMEOUT
        )
        self._groq_key = (groq_api_key or os.getenv("GROQ_API_KEY", "")).strip()
        self._gemini_key = (
            gemini_api_key or os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
        ).strip()
        self.enabled = bool(enabled)
        self.scout_models: List[str] = list(scout_models) if scout_models else list(SCOUT_MODELS)
        self.auditor_models: List[str] = list(auditor_models) if auditor_models else list(AUDITOR_MODELS)
        self.risk_engine: RiskEngine = risk_engine or RiskEngine()
        self._groq_client: Any = None
        self._gemini_client: Any = None
        self._runner: Optional[_Runner] = None
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #
    @property
    def scout_available(self) -> bool:
        return bool(self.enabled and self._groq_key)

    @property
    def auditor_available(self) -> bool:
        return bool(self.enabled and self._gemini_key)

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "scout": self.scout_available,
            "auditor": self.auditor_available,
            "scout_models": list(self.scout_models),
            "auditor_models": list(self.auditor_models),
            "timeout": self.timeout,
            "auditor_timeout": self.auditor_timeout,
        }

    def configure(self, groq_api_key: Optional[str] = None, gemini_api_key: Optional[str] = None) -> None:
        """Point the council at new keys. Resets any cached clients."""
        with self._lock:
            if groq_api_key is not None:
                self._groq_key = groq_api_key.strip()
                self._groq_client = None
            if gemini_api_key is not None:
                self._gemini_key = gemini_api_key.strip()
                self._gemini_client = None

    def close(self) -> None:
        with self._lock:
            if self._runner is not None:
                self._runner.close()
                self._runner = None

    # ------------------------------------------------------------------ #
    # Entry points
    # ------------------------------------------------------------------ #
    def assess(self, setup: Dict[str, Any]) -> RiskAssessment:
        """Deterministic risk gate only (no network)."""
        return self.risk_engine.assess(setup)

    def evaluate(self, setup: Dict[str, Any]) -> CouncilVerdict:
        """Blocking wrapper for Streamlit. Always returns within ~timeout + margin."""
        try:
            runner = self._ensure_runner()
            margin = max(self.timeout, self.auditor_timeout) + 3.0
            return runner.run(self.deliberate(setup), timeout=margin)
        except Exception as exc:  # noqa: BLE001 - never let the UI crash
            LOGGER.warning("council evaluate failed open: %s", exc)
            verdict = CouncilVerdict()
            verdict.risk = self.risk_engine.assess(setup)
            verdict.rrr_ok = verdict.risk.rrr_ok
            verdict.approved = verdict.risk.allowed
            verdict.verdict = verdict.risk.direction
            verdict.messages.append(f"Council error: {exc}")
            return verdict

    def _ensure_runner(self) -> _Runner:
        with self._lock:
            if self._runner is None:
                self._runner = _Runner()
            return self._runner

    async def deliberate(self, setup: Dict[str, Any]) -> CouncilVerdict:
        """Assess + review ``setup`` with both counselors in parallel. Never raises."""
        started = time.monotonic()
        verdict = CouncilVerdict()
        verdict.risk = self.risk_engine.assess(setup)
        verdict.rrr_ok = verdict.risk.rrr_ok
        verdict.verdict = verdict.risk.direction
        verdict.summary = "Deterministic risk gate applied."
        if not self.enabled:
            verdict.messages.append("LLM council disabled - risk engine only.")
            self._blend(verdict)
            verdict.elapsed_ms = int((time.monotonic() - started) * 1000)
            return verdict

        coros: List[Any] = []
        labels: List[str] = []
        if self.scout_available:
            coros.append(self._call_scout(setup))
            labels.append("scout")
        else:
            verdict.messages.append("Scout offline (no Groq API key).")
        if self.auditor_available:
            coros.append(self._call_auditor(setup))
            labels.append("auditor")
        else:
            verdict.messages.append("Risk Auditor offline (no Gemini API key).")

        if coros:
            results = await asyncio.gather(*coros, return_exceptions=True)
            for label, result in zip(labels, results):
                if isinstance(result, BaseException):
                    LOGGER.warning("%s failed open: %s", label, result)
                    verdict.messages.append(f"{label} error: {result}")
                    continue
                if label == "scout":
                    verdict.scout = result
                else:
                    verdict.auditor = result
                if not result.ok:
                    verdict.messages.append(f"{label} unavailable: {result.error or 'unknown error'}")

        self._blend(verdict)
        verdict.elapsed_ms = int((time.monotonic() - started) * 1000)
        return verdict

    # ------------------------------------------------------------------ #
    # Blending
    # ------------------------------------------------------------------ #
    @staticmethod
    def _blend(verdict: CouncilVerdict) -> None:
        if verdict.scout is not None and verdict.scout.ok:
            verdict.scout_model_used = verdict.scout.model
        if verdict.auditor is not None and verdict.auditor.ok:
            verdict.auditor_model_used = verdict.auditor.model

        risk = verdict.risk
        hard_ok = risk.allowed if risk is not None else verdict.rrr_ok

        opinions = [o for o in (verdict.scout, verdict.auditor) if o is not None and o.ok]
        if not opinions:
            # Fail-open: with no usable LLM opinion the deterministic gate alone decides.
            verdict.degraded = True
            verdict.approved = hard_ok
            if risk is not None:
                verdict.verdict = risk.direction
                verdict.confidence = 0.5 if hard_ok else 0.0
            verdict.summary = (
                "LLMs unavailable - deterministic Risk Auditor is authoritative."
            )
            verdict.notes = "; ".join(risk.messages) if risk is not None else "No LLM opinion available."
            return

        verdict.degraded = len(opinions) < 2
        verdict.fallback_used = any(o.fallback for o in opinions)
        for opinion in opinions:
            if opinion.fallback:
                verdict.messages.append(f"{opinion.role}: fallback model '{opinion.model}' answered.")

        primary = next((o for o in opinions if o.role == "Risk Auditor"), opinions[-1])
        verdict.confidence = sum(o.confidence for o in opinions) / len(opinions)
        verdict.summary = primary.summary or opinions[0].summary
        verdict.notes = (verdict.auditor.summary if verdict.auditor and verdict.auditor.ok else "") or verdict.summary

        # The deterministic Risk Auditor owns direction and approval; the LLM Scout
        # may only supply a direction when the gate found no signal of its own.
        if risk is not None and risk.direction != "neutral":
            verdict.verdict = risk.direction
        elif verdict.scout is not None and verdict.scout.ok:
            verdict.verdict = verdict.scout.verdict

        auditor = verdict.auditor
        if auditor is not None and auditor.ok and auditor.compliant is False:
            verdict.approved = False
            verdict.messages.append("Risk Auditor flagged a compliance breach.")
        elif risk is not None and not risk.allowed:
            verdict.approved = False
            for reason in risk.lock_reasons or risk.messages[:2]:
                verdict.messages.append(reason)
        else:
            verdict.approved = hard_ok

        votes = {o.verdict for o in opinions}
        verdict.consensus = len(votes) == 1
        verdict.messages.append(
            f"Council {'consensus' if verdict.consensus else 'split'} -> {verdict.verdict}."
        )

    # ------------------------------------------------------------------ #
    # Counselors (model cascades)
    # ------------------------------------------------------------------ #
    async def _call_scout(self, setup: Dict[str, Any]) -> CounselorOpinion:
        return await self._run_cascade(
            "Scout", "groq", self.scout_models, lambda m: self._scout_once(m, setup)
        )

    async def _call_auditor(self, setup: Dict[str, Any]) -> CounselorOpinion:
        # Dedicated budget so a single Gemini request can run up to AUDITOR_TIMEOUT
        # (10s) instead of the ~2.5s slice the shared scout deadline used to grant.
        return await self._run_cascade(
            "Risk Auditor", "gemini", self.auditor_models,
            lambda m: self._auditor_once(m, setup),
            timeout=self.auditor_timeout,
            per_call_timeout=self.auditor_timeout,
        )

    async def _run_cascade(
        self,
        role: str,
        provider: str,
        models: Sequence[str],
        make_call: Callable[[str], Awaitable[CounselorOpinion]],
        timeout: Optional[float] = None,
        per_call_timeout: Optional[float] = None,
    ) -> CounselorOpinion:
        """Try each model in order under one shared hard deadline. Never raises.

        ``timeout`` overrides the shared deadline (defaults to ``self.timeout``).
        ``per_call_timeout``, when set, caps each attempt at that many seconds
        rather than splitting the deadline evenly across the remaining models -
        used to give the Gemini Risk Auditor its full 10s request budget.
        """
        cascade = list(models) or [""]
        deadline = time.monotonic() + (timeout if timeout and timeout > 0 else self.timeout)
        attempted: List[str] = []
        last_error = ""

        for index, model in enumerate(cascade):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                last_error = last_error or "time budget exhausted"
                break
            if per_call_timeout and per_call_timeout > 0:
                budget = min(remaining, per_call_timeout)
            else:
                budget = remaining / max(1, len(cascade) - index)
            attempted.append(model)
            try:
                opinion = await asyncio.wait_for(make_call(model), timeout=budget)
            except asyncio.TimeoutError:
                last_error = f"{model}: timed out after {budget:.1f}s"
                LOGGER.warning("%s '%s' timed out; next fallback.", role, model)
                continue
            except Exception as exc:  # noqa: BLE001
                last_error = f"{model}: {exc}"
                LOGGER.warning("%s '%s' failed (%s); next fallback.", role, model, exc)
                continue
            if not isinstance(opinion, CounselorOpinion):
                last_error = f"{model}: malformed response"
                continue
            opinion.model = model
            opinion.attempted = list(attempted)
            opinion.fallback = index > 0
            return opinion

        return CounselorOpinion(
            role=role, provider=provider, model=cascade[0],
            ok=False, error=last_error or "no model available", attempted=list(attempted),
        )

    async def _scout_once(self, model: str, setup: Dict[str, Any]) -> CounselorOpinion:
        if self._groq_client is None:
            from groq import AsyncGroq

            self._groq_client = AsyncGroq(api_key=self._groq_key)
        response = await self._groq_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SCOUT_SYSTEM},
                {"role": "user", "content": _format_setup(setup)},
            ],
            temperature=0.2,
            max_tokens=400,
        )
        try:
            text = response.choices[0].message.content or ""
        except (AttributeError, IndexError, TypeError):
            text = ""
        return _opinion_from_text("Scout", "groq", model, text)

    async def _auditor_once(self, model: str, setup: Dict[str, Any]) -> CounselorOpinion:
        if self._gemini_client is None:
            from google import genai

            self._gemini_client = genai.Client(api_key=self._gemini_key)
        response = await self._gemini_client.aio.models.generate_content(
            model=model, contents=f"{_AUDITOR_SYSTEM}\n\n{_format_setup(setup)}"
        )
        return _opinion_from_text("Risk Auditor", "gemini", model, getattr(response, "text", "") or "")


# --------------------------------------------------------------------------- #
# LLM response parsing
# --------------------------------------------------------------------------- #
def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _clamp_confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.5
    if number > 1.0:
        number = number / 100.0
    return max(0.0, min(1.0, number))


def _format_setup(setup: Dict[str, Any]) -> str:
    return "Trade setup under review:\n" + "\n".join(
        f"- {k}: {v}" for k, v in setup.items() if v is not None and k not in {"now", "spec"}
    )


def _opinion_from_text(role: str, provider: str, model: str, text: str) -> CounselorOpinion:
    data = _extract_json(text)
    if data is None:
        return CounselorOpinion(
            role=role, provider=provider, model=model, verdict="neutral", confidence=0.5,
            summary=(text or "").strip()[:400] or "No usable response.", ok=True, raw=text or "",
        )
    compliant: Optional[bool] = None
    if "compliant" in data:
        compliant = bool(data.get("compliant"))
    return CounselorOpinion(
        role=role, provider=provider, model=model,
        verdict=_normalize_direction(data.get("verdict")),
        confidence=_clamp_confidence(data.get("confidence")),
        summary=str(data.get("summary", "")).strip()[:400],
        compliant=compliant, ok=True, raw=text or "",
    )


__all__ = [
    "SentinelCouncil",
    "CouncilVerdict",
    "CounselorOpinion",
    "RiskEngine",
    "RiskAssessment",
    "Session",
    "LONDON_OPEN",
    "LONDON_NY_OVERLAP",
    "PRIMARY_SESSIONS",
    "active_sessions",
    "session_ok",
    "size_lot",
    "SCOUT_MODELS",
    "AUDITOR_MODELS",
    "DEFAULT_TIMEOUT",
    "ACCOUNT_SIZE_USD",
    "ACCOUNT_SIZE_MAX_USD",
    "RISK_PER_TRADE_USD",
    "MIN_RRR",
    "MIN_TP_USD",
    "MAX_TRADES_PER_DAY",
    "DAILY_LOSS_LOCK_USD",
    "DAILY_LOSS_KILL_USD",
    "DAILY_PROFIT_TARGET_USD",
]
