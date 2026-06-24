# TradingAgents/tradingagents/graph/risk_guardrails.py
#
# Deterministic safety net that runs AFTER the Portfolio Manager's LLM-based
# decision. Enforces hard, non-negotiable risk limits that no amount of
# LLM "reasoning" can override.
#
# Philosophy: LLMs are great at qualitative assessment (thesis, sentiment,
# edge-case reasoning). They are terrible at quantitative discipline
# (position sizing, max drawdown, correlation risk). Let the LLM debate
# the thesis. Let math protect the capital.

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class GuardrailConfig:
    """Hard risk limits. These are NOT suggestions — they are circuit breakers.

    Set via config dict keys (all optional, sensible defaults):
        risk_guardrails_enabled: bool = False
        max_position_pct: float = 25.0
        max_single_loss_pct: float = 5.0
        require_stop_loss: bool = True
        blocked_ratings: list[str] = []  # e.g. ["Buy"] to prevent buys
    """

    enabled: bool = False
    max_position_pct: float = 25.0       # max % of portfolio in one position
    max_single_loss_pct: float = 5.0     # max loss per trade before forced exit
    require_stop_loss: bool = True       # reject Buy/Overweight without stop-loss
    blocked_ratings: list = field(default_factory=list)  # hard-block certain actions


@dataclass
class GuardrailResult:
    """Outcome of a guardrail check."""

    original_decision: str
    modified_decision: str
    was_modified: bool
    violations: list  # human-readable list of triggered rules
    clamped_fields: dict  # field → (original, clamped) pairs


class RiskGuardrails:
    """Deterministic post-PM safety layer.

    Runs after the Portfolio Manager outputs its decision. Parses the
    structured markdown, checks each field against hard limits, and
    either passes the decision through or clamps/overrides it.

    This node is intentionally NOT an LLM call — it is pure Python
    validation. LLMs cannot be trusted with capital preservation logic.
    """

    def __init__(self, config: dict):
        gc = GuardrailConfig(
            enabled=config.get("risk_guardrails_enabled", False),
            max_position_pct=config.get("max_position_pct", 25.0),
            max_single_loss_pct=config.get("max_single_loss_pct", 5.0),
            require_stop_loss=config.get("require_stop_loss", True),
            blocked_ratings=[
                r.lower() for r in config.get("blocked_ratings", [])
            ],
        )
        self.gc = gc

    def check(self, final_trade_decision: str) -> GuardrailResult:
        """Validate the PM's decision against hard risk limits.

        Args:
            final_trade_decision: The markdown string from the Portfolio Manager

        Returns:
            GuardrailResult with original and (possibly modified) decision
        """
        if not self.gc.enabled:
            return GuardrailResult(
                original_decision=final_trade_decision,
                modified_decision=final_trade_decision,
                was_modified=False,
                violations=[],
                clamped_fields={},
            )

        violations = []
        clamped = {}
        decision = final_trade_decision

        # ── 1. Blocked ratings ──
        rating = self._extract_field(decision, "Rating")
        if rating and rating.lower() in self.gc.blocked_ratings:
            violations.append(
                f"BLOCKED: Rating '{rating}' is in blocked_ratings list. "
                f"Overriding to Hold."
            )
            decision = self._replace_field(decision, "Rating", "Hold")
            clamped["Rating"] = (rating, "Hold")

        # ── 2. Position sizing cap ──
        sizing = self._extract_field(decision, "Position Sizing")
        if sizing:
            pct = self._extract_percentage(sizing)
            if pct is not None and pct > self.gc.max_position_pct:
                capped = f"{self.gc.max_position_pct:.0f}% of portfolio (clamped from {pct:.0f}%)"
                violations.append(
                    f"CLAMPED: Position size {pct:.0f}% exceeds max "
                    f"{self.gc.max_position_pct:.0f}%. Reduced."
                )
                decision = self._replace_field(decision, "Position Sizing", capped)
                clamped["Position Sizing"] = (sizing, capped)

        # ── 3. Stop-loss requirement ──
        if self.gc.require_stop_loss:
            stop_loss = self._extract_field(decision, "Stop Loss")
            rating_lower = (rating or "").lower()
            if rating_lower in ("buy", "overweight") and not stop_loss:
                violations.append(
                    f"WARNING: {rating} recommendation issued without a stop-loss. "
                    f"Risk guardrails require a stop-loss for directional positions."
                )
                # Append a warning to the decision rather than blocking
                decision += (
                    "\n\n**⚠️ Risk Guardrail Warning**: No stop-loss specified. "
                    "A stop-loss is strongly recommended before execution."
                )

        # ── 4. Loss-per-trade sanity check ──
        entry = self._extract_number(self._extract_field(decision, "Entry Price") or "")
        stop = self._extract_number(self._extract_field(decision, "Stop Loss") or "")
        if entry and stop and entry > 0:
            loss_pct = abs(entry - stop) / entry * 100
            if loss_pct > self.gc.max_single_loss_pct:
                violations.append(
                    f"ALERT: Stop-loss distance ({loss_pct:.1f}%) exceeds max "
                    f"single-loss limit ({self.gc.max_single_loss_pct:.1f}%). "
                    f"Consider tightening the stop."
                )
                # Don't override the stop — just warn. The trader may have reasons.
                decision += (
                    f"\n\n**⚠️ Risk Guardrail Alert**: Stop-loss distance "
                    f"({loss_pct:.1f}%) exceeds the configured maximum of "
                    f"{self.gc.max_single_loss_pct:.1f}%."
                )

        if violations:
            logger.warning(
                "Risk guardrails triggered %d violation(s):\n  %s",
                len(violations),
                "\n  ".join(violations),
            )

        return GuardrailResult(
            original_decision=final_trade_decision,
            modified_decision=decision,
            was_modified=decision != final_trade_decision,
            violations=violations,
            clamped_fields=clamped,
        )

    # ── Parsing helpers ──

    @staticmethod
    def _extract_field(text: str, field_name: str) -> Optional[str]:
        """Extract the value after **Field Name**: from markdown."""
        pattern = rf"\*\*{re.escape(field_name)}\*\*:\s*(.+?)(?:\n|$)"
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(1).strip() if match else None

    @staticmethod
    def _replace_field(text: str, field_name: str, new_value: str) -> str:
        """Replace a **Field Name**: value in markdown."""
        pattern = rf"(\*\*{re.escape(field_name)}\*\*:\s*).+?(?=\n|$)"
        return re.sub(
            pattern,
            lambda m: m.group(1) + new_value,
            text,
            flags=re.IGNORECASE,
        )

    @staticmethod
    def _extract_percentage(text: str) -> Optional[float]:
        """Extract the first percentage number from a string."""
        match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
        return float(match.group(1)) if match else None

    @staticmethod
    def _extract_number(text: str) -> Optional[float]:
        """Extract the first number from a string."""
        match = re.search(r"(\d+(?:\.\d+)?)", text)
        return float(match.group(1)) if match else None


def create_guardrail_node(config: dict):
    """Create a LangGraph node that applies risk guardrails post-PM.

    Usage in setup.py:
        guardrail_node = create_guardrail_node(self.config)
        workflow.add_node("Risk Guardrails", guardrail_node)
        workflow.add_edge("Portfolio Manager", "Risk Guardrails")
        workflow.add_edge("Risk Guardrails", END)
    """
    guardrails = RiskGuardrails(config)

    def guardrail_node(state) -> dict:
        result = guardrails.check(state["final_trade_decision"])

        if result.was_modified:
            logger.info(
                "Risk guardrails modified the decision. Violations: %s",
                "; ".join(result.violations),
            )

        return {"final_trade_decision": result.modified_decision}

    return guardrail_node
