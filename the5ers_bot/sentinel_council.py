"""
sentinel_council.py
===================
Two-model "Sentinel Council" that reviews a manual trade setup before the trader
places it in MT5. The council is **advisory only** - it never sends orders.

* **Scout** (Groq) - reads trend / momentum / chart structure (EMA50 vs EMA200,
  RSI posture, ATR context) and proposes LONG / SHORT / NEUTRAL.
* **Risk Auditor** (Gemini) - validates the setup against the The5ers $2,500 High
  Stakes budget: 1R = $10, target +$30 (RRR >= 1:3), +$40 daily ceiling and a
  -$50 daily kill-switch, and confirms the recommended lot stays 0.01-0.02.

Resilience
----------
Both counselors walk a prioritised model cascade and fall through to the next
model on any API error, rate-limit or timeout:

* Scout (Groq)         : ``openai/gpt-oss-120b`` -> ``qwen/qwen3.8-27b`` -> ``openai/gpt-oss-20b``
* Risk Auditor (Gemini): ``gemini-2.5-flash`` -> ``gemini-2.5-flash-lite`` -> ``gemini-3.8-flash``

The whole cascade shares one hard deadline (``DEFAULT_TIMEOUT`` = 8s). If a provider
dies outright the survivor carries the verdict; if both fail (or keys are absent)
the council fails **open** (``approved=True``) so it can never block the trader.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

LOGGER = logging.getLogger("copilot.council")

DEFAULT_TIMEOUT = 8.0

# Hard rule: every approved setup must clear a 1:3 reward-to-risk floor.
MIN_RRR = 3.0

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

VALID_VERDICTS = {"long", "short", "neutral"}

_SCOUT_SYSTEM = (
    "You are Scout, a technical analyst on a manual day/swing trading desk. Judge the "
    "momentum and structure of the setup using the provided EMA50/EMA200 relationship, "
    "RSI(14) and ATR context. Answer LONG, SHORT or NEUTRAL and be decisive. "
    'Reply with ONLY JSON: {"verdict":"long"|"short"|"neutral","confidence":0.0-1.0,'
    '"summary":"one short sentence"}.'
)

_AUDITOR_SYSTEM = (
    "You are the Risk Auditor for a The5ers $2,500 High Stakes evaluation account. "
    "Hard rules: risk per trade is 1R = $10, the take-profit must be at least 3x the "
    "stop (RRR >= 1:3, i.e. >= $30), the daily profit ceiling is +$40 and the daily "
    "kill-switch is -$50. Recommended lot size must stay within 0.01-0.02. Validate the "
    "setup against these rules using the reported numbers. Be conservative. "
    'Reply with ONLY JSON: {"verdict":"long"|"short"|"neutral","confidence":0.0-1.0,'
    '"compliant":true|false,"summary":"one short sentence of auditor notes"}.'
)


# --------------------------------------------------------------------------- #
# Parsing helpers
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


def _normalize_verdict(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in VALID_VERDICTS:
        return text
    if text.startswith("l") or text in {"buy", "bullish", "up"}:
        return "long"
    if text.startswith("s") or text in {"sell", "bearish", "down"}:
        return "short"
    return "neutral"


def _clamp_confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.5
    if number > 1.0:
        number = number / 100.0
    return max(0.0, min(1.0, number))


def _format_setup(setup: Dict[str, Any]) -> str:
    return "Trade setup under review:\n" + "\n".join(f"- {k}: {v}" for k, v in setup.items() if v is not None)


# --------------------------------------------------------------------------- #
# Data objects
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
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        return data


# --------------------------------------------------------------------------- #
# Sync bridge (own event loop thread, mirrors metaapi_client._AsyncRunner)
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
    """Async multi-LLM council with model fallback. Fail-open, advisory only."""

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        groq_api_key: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        enabled: bool = True,
        scout_models: Optional[Sequence[str]] = None,
        auditor_models: Optional[Sequence[str]] = None,
    ) -> None:
        self.timeout = float(timeout) if timeout and timeout > 0 else DEFAULT_TIMEOUT
        self._groq_key = (groq_api_key or os.getenv("GROQ_API_KEY", "")).strip()
        self._gemini_key = (
            gemini_api_key or os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
        ).strip()
        self.enabled = bool(enabled)
        self.scout_models: List[str] = list(scout_models) if scout_models else list(SCOUT_MODELS)
        self.auditor_models: List[str] = list(auditor_models) if auditor_models else list(AUDITOR_MODELS)
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
    # Sync + async entry points
    # ------------------------------------------------------------------ #
    def evaluate(self, setup: Dict[str, Any]) -> CouncilVerdict:
        """Blocking wrapper for Streamlit. Always returns within ~timeout + margin."""
        try:
            runner = self._ensure_runner()
            return runner.run(self.deliberate(setup), timeout=self.timeout + 3.0)
        except Exception as exc:  # noqa: BLE001 - never let the UI crash
            LOGGER.warning("council evaluate failed open: %s", exc)
            verdict = CouncilVerdict()
            verdict.rrr_ok = _rrr_ok(setup)
            verdict.messages.append(f"Council error: {exc}")
            return verdict

    def _ensure_runner(self) -> _Runner:
        with self._lock:
            if self._runner is None:
                self._runner = _Runner()
            return self._runner

    async def deliberate(self, setup: Dict[str, Any]) -> CouncilVerdict:
        """Review ``setup`` with both counselors in parallel. Never raises."""
        started = time.monotonic()
        verdict = CouncilVerdict(rrr_ok=_rrr_ok(setup))
        if not self.enabled:
            verdict.messages.append("Council disabled.")
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

        opinions = [o for o in (verdict.scout, verdict.auditor) if o is not None and o.ok]
        if not opinions:
            # Fail-open: with no usable opinion the deterministic RRR gate alone
            # decides, and we never block the trader.
            verdict.degraded = True
            verdict.approved = True
            verdict.verdict = "neutral"
            verdict.confidence = 0.0
            verdict.summary = "Council unavailable - deferring to the deterministic RRR check."
            verdict.notes = "No LLM opinion available."
            return

        verdict.degraded = len(opinions) < 2
        verdict.fallback_used = any(o.fallback for o in opinions)
        for opinion in opinions:
            if opinion.fallback:
                verdict.messages.append(f"{opinion.role}: fallback model '{opinion.model}' answered.")

        primary = next((o for o in opinions if o.role == "Risk Auditor"), opinions[-1])
        verdict.verdict = primary.verdict
        verdict.confidence = sum(o.confidence for o in opinions) / len(opinions)
        verdict.summary = primary.summary or opinions[0].summary
        verdict.notes = (verdict.auditor.summary if verdict.auditor and verdict.auditor.ok else "") or verdict.summary

        auditor = verdict.auditor
        auditor_ok = auditor is not None and auditor.ok
        if auditor_ok and auditor.compliant is False:
            verdict.approved = False
            verdict.messages.append("Risk Auditor flagged a compliance breach.")
        elif not verdict.rrr_ok:
            verdict.approved = False
            verdict.messages.append(f"Setup fails the hard RRR floor (>= 1:{MIN_RRR:g}).")
        else:
            verdict.approved = True

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
        return await self._run_cascade(
            "Risk Auditor", "gemini", self.auditor_models, lambda m: self._auditor_once(m, setup)
        )

    async def _run_cascade(
        self,
        role: str,
        provider: str,
        models: Sequence[str],
        make_call: Callable[[str], Awaitable[CounselorOpinion]],
    ) -> CounselorOpinion:
        """Try each model in order under one shared hard deadline. Never raises."""
        cascade = list(models) or [""]
        deadline = time.monotonic() + self.timeout
        attempted: List[str] = []
        last_error = ""

        for index, model in enumerate(cascade):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                last_error = last_error or "time budget exhausted"
                break
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


def _rrr_ok(setup: Dict[str, Any]) -> bool:
    """Deterministic 1:3 gate - always available even when the LLMs are offline."""
    try:
        rrr = float(setup.get("rrr", 0.0) or 0.0)
    except (TypeError, ValueError):
        return False
    return rrr >= MIN_RRR


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
        verdict=_normalize_verdict(data.get("verdict")),
        confidence=_clamp_confidence(data.get("confidence")),
        summary=str(data.get("summary", "")).strip()[:400],
        compliant=compliant, ok=True, raw=text or "",
    )


__all__ = [
    "SentinelCouncil",
    "CouncilVerdict",
    "CounselorOpinion",
    "SCOUT_MODELS",
    "AUDITOR_MODELS",
    "DEFAULT_TIMEOUT",
    "MIN_RRR",
]
